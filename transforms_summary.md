# Transforms Summary

This document summarizes all testability-pattern transforms in the dataset (excluding 0\_reflected\_xss as baseline, 102\_command\_injection, and 103\_path\_traversal). For each transform, a brief introduction of the pattern is given, one still-vulnerable example instance is shown, and a note on language transferability is included.

---

## Baseline: Original Reflected-XSS Sample (Transform 0\)

The baseline pattern is a classic server-side reflected XSS in a Node.js HTTP server. User input is taken directly from a URL query string (`query.name`) and written back to the HTTP response without any sanitization or encoding. The server reads the `name` parameter from the GET request and reflects it verbatim in the HTML response body, allowing an attacker to inject arbitrary HTML or JavaScript that is executed in the victim's browser.

**File:** `0_reflected_xss/server.js`

```javascript
var http = require('http');
var fs = require('fs');
var route = require('url');
const querystring = require('querystring');

function handleServer(req, res){
    var path = route.parse(req.url, true);

    if(req.url === '/'){
        res.writeHead(200, {"Content-Type" : "text/html"});
        fs.createReadStream('./index.html').pipe(res);
    }else if(path.pathname === '/query/'){
        const parsed = route.parse(req.url);
        const query  = querystring.parse(parsed.query);
        res.writeHead(200, {"Content-Type" : "text/html"});
        res.write(query.name);   // <-- XSS: unsanitized user input reflected directly
        res.end();
    }else{
        res.writeHead(404, {"Content-Type": "text/plain"});
        res.end('Page not found');
    }
}

http.createServer(handleServer).listen(8080);
```

---

## Transform 1 — Unset Element from Array

**Pattern:** In PHP, `(array)$variable` casts a value as an array and `unset($array[i])` removes elements. JavaScript has no native type-casting unset; instead, `Array.prototype.splice()` is used to remove elements by index. The testability pattern tests whether SAST tools can track taint through an array after a `splice` call that does **not** remove the tainted element (i.e., the splice index falls after the tainted position).

**Vulnerable example (Instance 2):**

```javascript
var c = query.name;
array = ['a', 'b', c, 'd'];
array.splice(3, 1);   // removes index 3 ('d'), leaving c at index 2
array.forEach(element => { res.write(element); });
```

**Language transferable?** Yes — Python uses `list.pop(index)` or `del list[i]`, C++ uses `vector::erase()`. The semantic of "remove element at index N but tainted data survives at a different index" applies to any language with indexed collections.

---

## Transform 2 — URI Encoding/Decoding

**Pattern:** The URI pattern tests whether SAST tools understand that `decodeURI()` does not sanitize user input — it merely reverses percent-encoding. An attacker can supply already-decoded input or input that remains harmful after decoding. By contrast, `encodeURI()` is a sanitizer (it encodes special characters). Tools must correctly distinguish the data flow through these two symmetrical-but-opposite functions.

**Vulnerable example (Instance 1):**

```javascript
const b = query.name;
res.write(decodeURI(b));   // decodeURI is NOT a sanitizer — XSS survives
```

**Language transferable?** Yes — Python has `urllib.parse.unquote()` (equivalent to `decodeURI`) and `urllib.parse.quote()` (equivalent to `encodeURI`). C++ uses libcurl's `curl_easy_unescape`. Same semantic applies.

---

## Transform 3 — Evaluated Call Time (Default Parameters)

**Pattern:** JavaScript evaluates default argument values at **call time**, creating a new object on each invocation. This pattern tests whether tools can track tainted data that is passed explicitly as a parameter that overrides a default expression. When the function is called with the tainted value as the third argument (overriding the computed default `greeting + ' ' + name`), the tainted data flows directly through to the return value.

**Vulnerable example (Instance 2):**

```javascript
function greet(name, greeting, message = greeting + ' ' + name){
    return message;
}
var m = greet('name', 'surname', query.name);
res.write(m);
```

**Language transferable?** Yes — Python evaluates default arguments at **definition** time (a notable difference), but the explicit override scenario is the same. C++ allows default parameters with similar semantics. The taint-flow challenge is language-agnostic.

---

## Transform 4 — Function Apply

**Pattern:** `Function.prototype.apply(thisArg, argsArray)` calls a function with a specified `this` context and arguments passed as an array. SAST tools must recognize that tainted data passed inside the arguments array to `apply()` flows through to the invoked function's parameters, which are then used in a sink.

**Vulnerable example (Instance 1):**

```javascript
function returnVal(x) { 
    return x; 
}
let b = query.name;
res.write(returnVal.apply(this, [b]));   // apply passes b as first arg — XSS
```

**Language transferable?** Yes — Python achieves the same via `func(*args)` unpacking. C++ uses `std::apply` or variadic template forwarding. The core taint-through-apply-call pattern translates directly.

---

## Transform 5 — Variadic / Rest Parameters

**Pattern:** The rest parameter syntax (`...numbers`) collects all remaining function arguments into an array. SAST tools must track that a tainted value passed as one of the arguments to such a function is collected into the rest array and subsequently processed (e.g., via `forEach`) before being written to a sink. The taint is "hidden" inside the aggregated array.

**Vulnerable example (Instance 1):**

```javascript
function sum(...numbers){
    numbers.forEach(out);
}
function out(val){ 
    res.write(val); 
}
sum('a', 'b', 'c', b);   // b = query.name flows into rest array → XSS
```

**Language transferable?** Yes — Python's `*args` is semantically identical. C++ variadic templates/`va_list` achieve the same effect. The pattern is language-agnostic.

---

## Transform 6 — Callback Function

**Pattern:** A function is assigned to a variable and passed as a first-class argument to another function, which then calls it dynamically. SAST tools need to resolve the dynamic dispatch — they must identify that the parameter `message` in `print(n, message)` refers to `MyFunction`, and therefore tainted data `n` flows through `message(n)` into the return value and subsequently to the sink.

**Vulnerable example (Instance 1):**

```javascript
function MyFunction(n) { 
    return n; 
}
function print(n, message) { 
    res.write(message(n)); 
}
var n = query.name;
print(n, MyFunction);   // callback carries taint — XSS
```

**Language transferable?** Yes — Python passes functions as first-class objects. C++ uses function pointers, `std::function`, or lambdas. The pattern translates to any language supporting higher-order functions.

---

## Transform 7 — Array Unshift

**Pattern:** `Array.prototype.unshift()` inserts elements at the **beginning** of an array, shifting existing elements to higher indices. Tainted input is inserted together with safe values; the resulting array is then iterated and all elements are written to the response. SAST tools must track that user-supplied data prepended via `unshift` is later output.

**Vulnerable example (Instance 1):**

```javascript
const b = query.name;
let myArray = new Array('1', '2', '3');
myArray.unshift('4', b);   // array becomes ['4', b, '1', '2', '3']
for(let i=0; i < myArray.length; i++) { 
    res.write(myArray[i]); 
}   // XSS
```

**Language transferable?** Yes — Python's `list.insert(0, value)` or `deque.appendleft()` are equivalent. C++ uses `std::deque::push_front()` or `vector::insert(begin(), ...)`.

---

## Transform 8 — Send Unpack (Spread in Call)

**Pattern:** The spread operator (`...array`) unpacks array elements as positional arguments to a function call. Tainted data is placed inside an array together with safe values; when the array is spread into a function call, tainted data arrives as a named parameter and is subsequently written to the sink. Tools must understand that `add(...a)` is equivalent to `add(a[0], a[1])`.

**Vulnerable example (Instance 1):**

```javascript
function add(a, b) { 
    res.write(a); 
    res.write(b); 
}
var b = query.name;
var a = ['a', b];
add(...a);   // spreads array: add('a', b) — XSS via second write
```

**Language transferable?** Yes — Python uses `func(*list)`. C++ uses fold expressions or `std::apply`. The concept of unpacking a collection into function arguments is universal. The transferred version to Python or C++ is similar to Transform 5\. So, we can merge the two transforms when using Python or C++.

---

## Transform 9 — Late Static Binding (Prototype Reassignment)

**Pattern:** JavaScript's prototype-based inheritance allows dynamic modification of an object's prototype chain at runtime. Assigning `my_class2.prototype = new my_class(a)` at runtime means that `my_class2` instances inherit the tainted `name` property from the injected prototype object. Tools must understand runtime prototype manipulation to follow the taint path.

**Vulnerable example (Instance 1):**

```javascript
function my_class(val) { 
    this.name = val; 
}
my_class.prototype.get_name = function() { 
    return this.name; 
}
function my_class2() { 
    this.name = "safe"; 
}
var a = query.name;
my_class2.prototype = new my_class(a);   // prototype carries taint
my_class_instance = new my_class2();
res.write(my_class2.prototype.name);   // XSS
```

**Language transferable?** Partially — Python uses class-level attribute manipulation (`MyClass.attr = value`) which achieves similar runtime prototype-like injection. C++ lacks dynamic prototype chains (static type system), making this specific technique not directly applicable. The general concept of runtime object mutation is transferable to Python but not C++.

---

## Transform 10 — Spread Properties (Object Spread)

**Pattern:** The object spread syntax (`{...obj1}`) creates a shallow clone of an object, copying all enumerable own properties. Tainted data stored in a property of the source object is copied into the new object; subsequent iteration over the cloned object's properties hits the sink. SAST tools must trace taint through property-copying spread operations.

**Vulnerable example (Instance 1):**

```javascript
const b = query.name;
let obj1 = { foo: 'bar', x: 42, y: b };
let clonedObj = { ...obj1 };   // b is copied to clonedObj.y
for(v in clonedObj) { 
    res.write(clonedObj[v]); 
}   // XSS
```

**Language transferable?** Yes — Python uses `{**dict1}` for dict spreading. C++ does not have native object-spread syntax, but `std::merge` or copy constructors serve the same purpose. The taint-through-property-copy concept is broadly transferable.

---

## Transform 11 — Closure Scope Chain

**Pattern:** Multiple levels of nested functions create a scope chain where the innermost function has access to all outer function parameters. Tainted data is passed to the outermost function and captured in its closure; each successive level of nesting passes control inward until the innermost function concatenates the captured values and returns them. Tools must trace taint across multiple closure boundaries.

**Vulnerable example (Instance 1):**

```javascript
function assign(val){
    return function(val2){
        return function(val3){
            return function(val4){ return val + val2 + val3 + val4; }
        }
    }
}
var b = query.name;
res.write(assign(b)(': this ')('is ')('input'));   // XSS via closure chain
```

**Language transferable?** Yes — Python closures work identically. C++ supports nested lambdas capturing outer variables. The multi-level closure pattern is language-agnostic.

---

## Transform 12 — NaN (isNaN check)

**Pattern:** `isNaN(x)` returns `true` when the argument is **not** a number — including when it is a string such as user-supplied XSS payloads. A naive "sanitization" that returns the input unchanged when it is not a number (thinking only numeric input is dangerous) is actually backwards: it returns the tainted string when it is most dangerous and returns a safe constant (`"number"`) only when the input is numeric.

**Vulnerable example (Instance 1):**

```javascript
function sanitise(x) {
    if (isNaN(x)) { 
        return x;   // returns tainted string — XSS
    }   
    return "number";
}
let b = query.name;
res.write(sanitise(b));
```

**Language transferable?** Partially — JavaScript `isNaN` performs coercion and accepts strings, while Python `math.isnan` and C++ `std::isnan` require numeric inputs (string inputs error or are invalid). The exact API behavior is not portable, but the underlying anti-pattern (mistaking a numeric predicate for sanitization) is transferable.

---

## Transform 13 — IIFE (Immediately Invoked Function Expression)

**Pattern:** An IIFE is a function expression that is defined and immediately called in a single expression: `(function(params){...}(args))`. Tainted data is passed as one of the arguments and written to the sink inside the immediately-executed body. SAST tools must recognize the IIFE syntax and treat it as a normal function call with its argument list mapped to its parameters.

**Vulnerable example (Instance 1):**

```javascript
var a = query.name;
(function(val, out) {
    out.write(val);   // XSS — val receives tainted a
    out.end();
}(a, res));
```

**Language transferable?** Yes — Python achieves similar patterns with `(lambda x: print(x))(user_input)`. C++ supports immediately-invoked lambdas: `([](auto x){ use(x); })(user_input)`. The IIFE concept is broadly transferable.

---

## Transform 14 — Template Literals

**Pattern:** JavaScript template literals (backtick strings) allow arbitrary expressions to be interpolated via `${expr}` syntax. When user input participates in a template literal expression that is passed to a sink, taint flows through the template construction. Tools that only look for string concatenation with `+` may miss template-literal interpolation as a taint-propagation path.

**Vulnerable example (Instance 1):**

```javascript
const b = query.name;
const a = 4;
res.write(`result is ${a + b}.`);   // XSS via template literal interpolation
```

**Language transferable?** Yes — Python f-strings (`f"result is {a + b}"`) are semantically identical. C++ uses `std::format` (C++20) or `snprintf`. Template/format string injection is a cross-language concern.

---

## Transform 15 — Reflect Delete

**Pattern:** `Reflect.deleteProperty(obj, prop)` dynamically removes a property from an object, analogous to the `delete` operator. When the property name to be deleted is provided as a variable (coming from user input as `query.prop`), a tainted value stored under a different property key may survive the deletion and be output. The tool must understand that dynamic deletion only removes the specified key, leaving other tainted properties intact.

**Vulnerable example (Instance 2):**

```javascript
const b = query.name;
const p = query.prop;
let o = {property1: b};
Reflect.deleteProperty(o, p);   // deletes whatever key p names, NOT necessarily 'property1'
for(i in o){ 
    res.write(o[i]);    // XSS if p !== 'property1'
} 
```

**Language transferable?** Partially — Python has `delattr(obj, name)` and `del dict[key]`. C++ lacks dynamic property deletion. The concept of conditional property removal is transferable to Python but not C++.

---

## Transform 16 — Nullish Coalescing Operator (??)

**Pattern:** The nullish coalescing operator `a ?? b` returns `b` only when `a` is `null` or `undefined`; otherwise it returns `a`. When the left operand is explicitly `null`, the right operand (user input `b`) becomes the result. Tools must understand this operator's semantics: unlike `||`, it does not treat `0`, `""`, or `false` as falsy, only `null`/`undefined`.

**Vulnerable example (Instance 1):**

```javascript
const b = query.name;
const nullValue = null;
const foo = nullValue ?? b;   // nullValue is null → foo receives b
res.write(foo);   // XSS
```

**Language transferable?** Partially — In Python we can use `noneValue or b` (no dedicated `??` operator). C++ lacks native null-coalescing syntax. The operator itself is JS-specific, but the logical pattern of "use fallback when primary is null" is universal.

---

## Transform 17 — Function.prototype.call()

**Pattern:** `func.call(thisArg, arg1, arg2, ...)` invokes a function with an explicitly specified `this` context. Tainted data is passed as a positional argument via `call()`, flows into the function body via its parameters, and is returned or used in a sink. SAST tools must treat `func.call(ctx, tainted)` as equivalent to `func(tainted)` for taint propagation.

**Vulnerable example (Instance 1):**

```javascript
var person = { 
    fullName: function(val) { 
        return this.firstName + " " + this.lastName + "," + val; 
    } 
};
const b = query.name;
var person1 = { firstName:"John", lastName: "Doe" };
res.write(person.fullName.call(person1, b));   // XSS — b flows through call
```

**Language transferable?** Yes — Python bound methods can be called with explicit `self` via `method.__func__(instance, arg)`. C++ member function pointers have similar semantics using `std::invoke`. The `call()` taint-propagation challenge is transferable.

---

## Transform 18 — Arguments Object

**Pattern:** Inside a non-arrow function, `arguments` is an array-like object containing all passed arguments, regardless of the formal parameter list. A function that accesses its input via `arguments[0]` rather than a named parameter may confuse SAST tools that do not model the implicit `arguments` object. Tainted data passed at the call site is accessible via `arguments` indexing.

**Vulnerable example (Instance 1):**

```javascript
function f(){ 
    return arguments[0];    // accesses input via 'arguments', not named param
}   
var a = query.name;
res.write(f(a));   // XSS — a flows through arguments[0]
```

**Language transferable?** No (for this exact construct) — JavaScript's implicit `arguments` object is JS-specific. Python's `*args` and C++ `va_list`/variadic templates are separate language features and are already covered by earlier variadic patterns, so Transform 18 itself is not directly transferable.

---

## Transform 19 — Nested Function

**Pattern:** A function `D` is declared inside an outer function `F` and then exposed as a property `F.D`. When `F()` is called first to initialize the nested structure and then `F.D(tainted)` is called, SAST tools must track that `F.D` refers to the nested `D` function, and that the argument flows through `D`'s parameter to the sink inside `D`.

**Vulnerable example (Instance 1):**

```javascript
function F(){
    function D(arg){ 
        res.write(arg); 
    }
    F.D = D;
}
var a = query.name;
F();
F.D(a);   // XSS — a flows through nested D via F.D property
```

**Language transferable?** Partially — Python supports nested functions and can expose an inner function via attributes, so the pattern maps closely. C++ can emulate parts of this with lambdas or function objects, but it has no direct equivalent to attaching a nested function as `F.D` on a function object. The exact mechanism is JS/Python-like, not idiomatic C++.

---

## Transform 20 — Long Function Call Chain (Too Many Function Calls)

**Pattern:** User input flows through a deeply nested call chain: `F → D → C → E → print`, where each function simply passes its argument to the next. SAST tools performing inter-procedural analysis with limited call-chain depth (k-callsite or k-CFA bounded) may lose track of taint after a certain number of hops, producing false negatives.

**Vulnerable example (Instance 1):**

```javascript
function F(a1){ 
    D(a1); 
    function D(a2){ 
        C(a2); 
        function C(a3){ 
            E(a3); 
            function E(a4){ 
                print(a4); 
            } 
        } 
    } 
}
function print(arg){ res.write(arg); }
var a = query.name;
F(a);   // XSS — taint travels through 4 levels of call chain
```

**Language transferable?** Yes — Python and C++ support arbitrarily deep call chains. The challenge of bounded inter-procedural taint tracking applies equally to all languages.

---

## Transform 21 — new.target

**Pattern:** `new.target` is a meta-property available inside a constructor or function; it evaluates to the function itself when called with `new`, or `undefined` otherwise. When a function is called **without** `new`, `new.target` is falsy and the body (which concatenates and outputs user input) is executed. Tools that do not model `new.target` may fail to determine which branch is taken at runtime.

**Vulnerable example (Instance 1):**

```javascript
function Foo(val){
    if(!new.target){ 
        res.write("cannot pass "+val+" to function without new"); 
    }
}
Foo(query.name);   // called without 'new' → condition true → XSS
```

**Language transferable?** No — `new.target` is a JavaScript-specific feature. Python and C++ have no equivalent meta-property distinguishing constructor vs. direct calls in this way.

---

## Transform 22 — Array Reduce

**Pattern:** `Array.prototype.reduce(callback, initialValue)` folds an array to a single accumulated value by repeatedly applying the callback. Tainted data placed inside the array is concatenated by the accumulator function and the final concatenated string is written to the sink. Tools must model that `reduce` propagates taint from any array element to the accumulated result.

**Vulnerable example (Instance 1):**

```javascript
var b = query.name;
var array = ['first', 'second', b];
let result = array.reduce(function(accumulator, currentValue){ 
    return accumulator + currentValue; 
}, ' ');
res.write(result);   // XSS — b is concatenated into result
```

**Language transferable?** Yes — Python has `functools.reduce()`. C++ has `std::accumulate`. The taint-through-fold pattern is universal.

---

## Transform 23 — forEach in Deeply Nested Functions

**Pattern:** `forEach` is called on an array inside a deeply nested function scope (4 levels deep). The callback `E` passed to `forEach` calls an outer-scope `print` function, which writes to the response. SAST tools with limited inter-procedural depth or incomplete `forEach` modeling may not connect the tainted array element to the sink inside the deeply nested callback chain.

**Vulnerable example (Instance 1):**

```javascript
function F(a1){ 
    D(a1); 
    function D(a2){ 
        C(a2); 
        function C(a3){
            var arr = ['1', a3];
            arr.forEach(E);
            function E(a4){ 
                print(a4); 
            }
        } 
    } 
}
function print(arg){ 
    res.write(arg); 
}
var a = query.name;
F(a);   // XSS — taint passes through nested forEach callback
```

**Language transferable?** Yes — Python uses `list.forEach` equivalents like `map()` or `for` loops inside nested functions. C++ has `std::for_each`. The deep-nesting challenge applies universally.

---

## Transform 24 — Finite (isFinite check)

**Pattern:** `isFinite(1000 / x)` checks whether the division result is a finite number. For non-numeric string inputs, `1000 / x` evaluates to `NaN` (not finite), causing the function to return a string that includes the original `x` via concatenation (`'Number ' + x + '...'`). The tainted input escapes through an arithmetic fallback path.

**Vulnerable example (Instance 1):**

```javascript
function div(x) {
    if (isFinite(1000 / x)) { 
        return 'Number ' + x + ' is NOT Infinity.'; 
    }
    return 'Number ' + x + ' is Infinity!';
}
let b = query.name;
res.write(div(b));   // XSS — both branches concatenate tainted x
```

**Language transferable?** Partially — JavaScript `isFinite` coerces strings (e.g., `1000 / "x"` becomes `NaN`), while Python `math.isfinite` and C++ `std::isfinite` require numeric inputs (string inputs must be parsed first or fail). The exact API behavior is not directly portable, but the anti-pattern of using a numeric predicate as a false security check remains transferable.

---

## Transform 25 — WeakMap

**Pattern:** A `WeakMap` uses object references as keys and can store arbitrary values. Tainted user input is stored in `wm2.set(obj1, b)`. Nested access `wm2.get(wm1).get(obj1)` returns the tainted value (because `wm2.set(wm1, wm2)` and `wm2.get(wm1)` returns `wm2` itself). Tools must track taint through WeakMap storage and nested retrieval chains.

**Vulnerable example (Instance 1):**

```javascript
const b = query.name;
const wm1 = new WeakMap(); 
const wm2 = new WeakMap();
const obj1 = {}, obj2 = function(){};
wm2.set(obj1, b);
wm2.set(wm1, wm2);
res.write(wm2.get(wm1).get(obj1));   // XSS — retrieves b via nested WeakMap lookup
```

**Language transferable?** Yes — Python has `weakref.WeakKeyDictionary`. C++ has no standard weak map, although `std::weak_ptr` combined with `std::map` achieves similar semantics, it requires complex implementation as `weak_ptr` does not have in-built `hash`. The taint-through-keyed-collection concept is transferable.

---

## Transform 26 — Computed Properties

**Pattern:** Object property names can be computed from expressions using bracket notation `{ [expr]: value }`. When the expression evaluates to a known key (e.g., `'b' + 'ar'` → `'bar'`), the tainted value stored under that computed key is retrievable via the resolved name (e.g., `o.bar`). Tools that do not evaluate constant expressions in computed property keys may fail to connect the store and load.

**Vulnerable example (Instance 1):**

```javascript
const b = query.name;
let o = {['b' + 'ar']: b};   // key evaluates to 'bar'
res.write(o.bar);   // XSS — b is stored under computed key 'bar'
```

**Language transferable?** Yes — Python uses `{expr: value}` for dict with computed keys. C++ uses `std::map[key] = value` where `key` can be any expression. The computed-key taint pattern is universal.

---

## Transform 27 — Cast String to Array

**Pattern:** In PHP, `(array)$var` casts a variable to an array. JavaScript has no direct cast syntax; instead, a common idiom is `arr = arr instanceof Array ? arr : [arr]` — if `arr` is not an array, wrap it in one. Since `query.name` returns a string (not an array), it gets wrapped in `[arr]`, and the tainted value is then output via `arr[0]`.

**Vulnerable example (Instance 1):**

```javascript
var arr = query.name;
arr = arr instanceof Array ? arr : [arr];   // string wrapped in array: [query.name]
res.write(arr[0]);   // XSS — arr[0] is the tainted string
```

**Language transferable?** Yes — Python uses `isinstance(x, list)` with similar wrapping idioms. C++ uses `std::variant` or runtime type checks. The type-guard-then-wrap pattern is broadly applicable.

---

## Transform 28 — Closures

**Pattern:** A closure is a function that captures variables from its enclosing lexical scope. `greet(name)` returns an inner function that, when called, returns the captured `name`. Tainted data is passed to `greet`, captured in the closure, and returned when the closure is invoked. Tools must track taint across the closure boundary — from the outer call site, through the captured variable, to the eventual sink.

**Vulnerable example (Instance 1):**

```javascript
function greet(name){ 
    return function(){ 
        return name; 
    }; 
}
var b = query.name;
var v = greet(b);
res.write(v(b));   // XSS — taint returns via closure-captured 'name'
```

**Language transferable?** Yes — Python closures work identically: inner functions capturing outer-scope variables. C++ lambdas capture by value or reference. Closures and their taint implications are universal.

---

## Transform 29 — Recursion via arguments.callee

**Pattern:** `arguments.callee` refers to the currently executing function itself, enabling anonymous recursion. Here the function calls itself once (guarded by a flag `b`), and on the recursive call, the second branch writes the tainted value. Tools must understand that `arguments.callee(val)` is a recursive self-call and that the tainted `val` flows through both calls.

**Vulnerable example (Instance 1):**

```javascript
var b = 0;
function rec(val){
    if(b === 0){ b = 1; arguments.callee(val); }
    else { res.write(val); }   // XSS on recursive call
}
var a = query.name;
rec(a);
```

**Language transferable?** Yes — Python supports named recursion. C++ supports recursion. The taint-through-recursion challenge (tracking that the argument on recursive calls is the same tainted value) is universal, even if `arguments.callee` itself is JS-specific.

---

## Transform 30 — Generator Delegation (yield\*)

**Pattern:** `yield*` delegates iteration to another generator function. Tainted input passed to `func2` is forwarded to `func1` via `yield* func1(val)`, and `func1` yields it directly. The caller then retrieves the yielded value via `.next().value` and writes it to the sink. Tools must trace taint through the `yield*` delegation chain across two generator functions.

**Vulnerable example (Instance 1):**

```javascript
function* func1(val) { 
    yield val; 
}
function* func2(val) { 
    yield* func1(val); 
}
var b_to_func = query.name;
const iterator = func2(b_to_func);
res.write(iterator.next().value);   // XSS — taint flows via yield* delegation
```

**Language transferable?** Partially — Python maps directly via yield from; C++ can emulate with coroutines/generator wrappers, but the mechanism is not as direct or idiomatic as in JS/Python.

---

## Transform 31 — GeneratorFunction Constructor

**Pattern:** A generator function can be created dynamically using `new GeneratorFunction(paramNames, body)`, analogous to `new Function()` but for generators. The resulting generator is called with tainted input; the dynamically constructed body `yield a` yields the argument directly. SAST tools typically cannot reason about code created via constructor-based dynamic function generation.

**Vulnerable example (Instance 1):**

```javascript
const b = query.name;
var GeneratorFunction = Object.getPrototypeOf(function*(){}).constructor;
var g = new GeneratorFunction('a', 'yield a');   // dynamically creates: function*(a){ yield a; }
var iterator = g(b);
res.write(iterator.next().value);   // XSS — b is yielded through dynamic generator
```

**Language transferable?** No — dynamic code construction via `new GeneratorFunction(...)` is JavaScript-specific. Python has `exec()`/`eval()` for dynamic code, and C++ has no runtime code generation in the standard language. The specific attack vector of dynamic generator construction is JS-only.

---

## Transform 32 — Array Shift

**Pattern:** `Array.prototype.shift()` removes and returns the **first** element of an array. When tainted user input is placed at position 0 of the array and `shift()` is called, the returned element is the tainted value, which is then written to the sink. Tools must model that `shift()` returns the first element and propagate taint accordingly.

**Vulnerable example (Instance 1):**

```javascript
const b = query.name;
let myArray = new Array(b, '1', '2');   // b is at index 0
element = myArray.shift();   // removes and returns b
res.write(element);   // XSS
```

**Language transferable?** Yes — Python uses `list.pop(0)`. C++ uses `std::deque::pop_front()` or `std::vector::erase(begin())`. The taint-through-first-element-removal pattern is universal.

---

## Transform 33 — Array Length Modification

**Pattern:** Assigning to `array.length` can either truncate or extend an array. When the tainted element is at a **lower index** than the new length, it survives the truncation. For example, `array = [b, 'first', 'second']; array.length = 2` keeps `b` at index 0 and `'first'` at index 1, removing only `'second'`. SAST tools must determine which elements survive after length reduction.

**Vulnerable example (Instance 2):**

```javascript
var b = query.name;
var array = [b, 'first', 'second'];
array.length = 2;   // keeps b at [0] and 'first' at [1], removes 'second'
for(let i = 0; i < array.length; i++) { 
    res.write(array[i]); 
}   // XSS
```

**Language transferable?** Yes — Python achieves truncation with `del list[n:]`. C++ uses `vector.resize(n)`. The general concept of tainted data surviving a partial collection truncation is universal.

---

## Transform 34 — Bind

**Pattern:** `Function.prototype.bind(thisArg, ...args)` creates a new function with a pre-bound `this` context (and optionally pre-bound arguments). When called with no arguments, `bind()` returns a new function equivalent to the original but with a new identity. Tainted data is passed when the bound function is eventually called; tools must trace through the `bind`\-created wrapper to the original function body.

**Vulnerable example (Instance 1):**

```javascript
function getX(x) { 
    return x; 
}
let b = query.name;
const boundGetX = getX.bind();   // creates a wrapper; no pre-bound args
res.write(boundGetX(b));   // XSS — b flows through bind wrapper to getX
```

**Language transferable?** Yes — Python has `functools.partial()`. C++ has `std::bind()`. Taint-through-bound-function-wrapper is a transferable pattern.

---

## Transform 35 — Async/Await

**Pattern:** An `async` function returns a `Promise`. `await` suspends execution until the awaited Promise resolves. Tainted input is passed into an `async` function, resolved via a `setTimeout`\-based Promise, and the resolved value is written to the response. Tools must track taint across asynchronous boundaries — through `Promise` resolution and `await` unwrapping.

**Vulnerable example (Instance 1):**

```javascript
function resolveAfter1Seconds(val) {
    return new Promise(resolve => { setTimeout(() => { resolve(val); }, 1000); });
}
async function asyncCall(val) {
    var result = await resolveAfter1Seconds(val);
    res.write(result);   // XSS — taint travels through async/await
}
asyncCall(query.name);
```

**Language transferable?** Yes — Python has `async/await` with `asyncio`. C++ has coroutines (C++20) including features like `co_wait`. Asynchronous taint propagation is a cross-language challenge, though the specific event-loop model differs.

---

## Transform 36 — Returned Function

**Pattern:** A function `f` receives tainted data and returns a closure (inner function) that, when invoked, returns the captured value. The caller immediately invokes the returned function: `f(a)()`. Tools must model that the returned function object encapsulates tainted state and that invoking it extracts and returns that tainted value.

**Vulnerable example (Instance 1):**

```javascript
function f(val) { 
    return function(){ return val; } 
}
var a = query.name;
res.write(f(a)());   // XSS — f(a) returns closure capturing a; ()() invokes it
```

**Language transferable?** Yes — Python closures work the same way: `def f(val): return lambda: val`. C++ lambdas support capture by value. The returned-closure taint pattern is universal.

---

## Transform 37 — Generators

**Pattern:** A generator function uses `yield` to produce values lazily. Tainted input is passed as the generator parameter; the body `yield b` inside a loop yields the tainted value on each iteration. The `for...of` loop that consumes the generator receives each yielded value and writes it to the sink. Tools must model the taint flow through `yield` and generator iteration.

**Vulnerable example (Instance 1):**

```javascript
function *gen_one_to_three(b) {
    for(i = 1; i <= 3; i++) { 
        yield b; 
    }
}
var b_to_func = query.name;
for (let n of gen_one_to_three(b_to_func)) {
    res.write(n);   // XSS — taint flows through yield
}
```

**Language transferable?** Yes — Python generators are semantically identical, using the same `yield` keyword. C++ coroutines (C++20) achieve similar behavior using features like `co_yield`. The taint-through-yield pattern is broadly applicable.

---

## Transform 38 — While Break (Dead Code)

**Pattern:** A `while(true)` loop increments an index and breaks immediately after the first iteration (`if(index === 1){ break; }`). The line `return_value = val` is **dead code** — it follows the break and is never executed. The function always returns the safe initial value `'returned_value'`. This is a **negative test case**: SAST tools that do not model break-induced dead code produce false positives here.

**Note:** All instances of this transform are NOT vulnerable (Vulnerable: NO). This transform demonstrates that tools incorrectly flag dead code after `break` as vulnerable.

**Example (Instance 1 — not vulnerable, demonstrates false positive):**

```javascript
function F(val){
    let return_value = 'returned_value';
    let index = 0;
    while(true){
        index++;
        if(index === 1) { 
            break; 
        }
        return_value = val;   // dead code — never reached
    }
    return return_value;   // always returns 'returned_value'
}
let b = query.name;
res.write(F(b));   // NOT XSS — dead code prevents taint from reaching sink
```

**Language transferable?** Yes — `while/break` with dead code is a universal control-flow pattern in Python and C++. The false-positive challenge of dead-code analysis is language-agnostic.

---

## Transform 39 — Function Get Arguments (Function Redeclaration)

**Pattern:** In JavaScript, a function can be redeclared with the same name but a different number of parameters. The second declaration replaces the first. SAST tools that model both declarations independently may generate false negatives or incorrect argument mappings. The active declaration has two parameters; calling `F('c', b)` passes tainted `b` as the second argument, which is written to the sink.

**Vulnerable example (Instance 1):**

```javascript
function F(a) { 
    res.write(a); 
}          // first declaration — overridden
function F(a, b) { 
    res.write(a); 
    res.write(b); 
}  // second declaration — active
var b = query.name;
F('c', b);   // XSS — b flows to write(b) in the active (second) F definition
```

**Language transferable?** Partially — Python does not allow function redeclaration in the same scope in the same syntactic way (the last assignment wins, similar to JS). C++ does not allow duplicate function definitions (only overloads with different signatures). The specific JS redeclaration semantic is partially transferable to Python but not C++.

---

## Transform 40 — Function Name Conflict (Variable Shadowing)

**Pattern:** The outer function `outer` has a local variable `x = 'safe'`. The inner function `insider(x)` has a **parameter** also named `x`, which shadows the outer `x` in `insider`'s scope. When `outer()` returns `insider` and it is called with tainted input, `insider`'s parameter `x` receives the tainted value — the safe outer `x` is irrelevant. Tools must correctly resolve which `x` is in scope.

**Vulnerable example (Instance 1):**

```javascript
function outer(){
    var x = 'safe';
    function insider(x) { 
        return x; 
    }   // parameter 'x' shadows outer 'x'
    return insider;
}
var a = query.name;
res.write(outer()(a));   // XSS — insider's 'x' receives tainted 'a', not outer's safe 'x'
```

**Language transferable?** Yes — variable shadowing is a universal concept in Python (local scope overrides enclosing/global) and C++ (inner-block declarations shadow outer ones). This is a fundamental taint-tracking challenge in all languages.

---

## Transform 41 — Symbol

**Pattern:** `Symbol.for(token)` looks up or creates a globally registered Symbol using `token` as the description key. `Symbol.keyFor(sym)` retrieves the string key associated with a registered Symbol. Tainted input passed to `Symbol.for()` becomes the key, and `Symbol.keyFor()` returns that same tainted string. Tools must model that `Symbol.keyFor(Symbol.for(x)) === x` for any string `x`.

**Vulnerable example (Instance 1):**

```javascript
function create(val) { 
    var sym = Symbol.for(val); 
    return sym; 
}
const b = query.name;
res.write(Symbol.keyFor(create(b)));   // XSS — keyFor returns the original tainted string
```

**Language transferable?** No — `Symbol` is a JavaScript-specific primitive type. Python and C++ have no equivalent mechanism where a string key is "wrapped" into a symbol and unwrapped verbatim. This pattern is JS-only.

---

## Transform 42 — Anonymous Object (Unnamed Class Expression)

**Pattern:** An anonymous class expression is instantiated immediately without being assigned a name: `(new class{ method(){...} })`. The result is an instance of the unnamed class, accessible via the assigned variable. Tainted input is passed to a method of the anonymous instance. SAST tools must recognize that `util` holds an instance of the anonymous class and that `util.log(b)` calls the `log` method which invokes `res.write(msg)`.

**Vulnerable example (Instance 1):**

```javascript
util = (new class{
    log(msg){ res.write(msg); }
})
var b = query.name;
util.log(b);   // XSS — log writes b via anonymous class method
```

**Language transferable?** Yes — Python supports anonymous class instantiation: `(type('', (), {'log': lambda self, msg: print(msg)})()).log(user_input)`. C++ supports inline struct/lambda with operator(). The anonymous-class pattern is transferable.

---

## Transform 43 — Window/Global Object

**Pattern:** In browser JS, `window` is the global object; in Node.js, `global` plays the same role. Assigning to `global.b = b` makes the tainted value accessible from any scope as `global.b`. A function `F()` that reads `global.b` inside its body gets the tainted value without it appearing in the function's parameter list. Tools must model global-object property reads as taint sources.

**Vulnerable example (Instance 1):**

```javascript
function F() { 
    res.write(global.b); 
}   // reads from global — XSS
var b = query.name;
global.b = b;   // tainted value stored in global namespace
F();
```

**Language transferable?** Partially — Python has `globals()['var'] = value` and implicit global variable access. C++ has global variables. The concept is transferable; the specific `global` object API is Node.js-specific.

---

## Transform 44 — Array Map

**Pattern:** `Array.prototype.map(callback)` creates a new array by applying `callback` to each element. Here the callback calls `func(x)` which invokes `res.write(a)` directly (side-effecting rather than returning a value). The tainted element in the input array is passed to `func` via the callback, and written to the response. Tools must trace taint through the `map` callback chain.

**Vulnerable example (Instance 1):**

```javascript
var b = query.name;
func = function(a){ res.write(a); };
var input = [b, b, b];
input.map(function(x){ func(x); });   // XSS — tainted b flows through map callback
```

**Language transferable?** Yes — Python has `list(map(func, iterable))`. C++ has `std::transform`. The taint-through-map-callback pattern is universal.

---

## Transform 45 — Escape / Unescape (Deprecated)

**Pattern:** `escape()` encodes a string (percent-encoding most non-ASCII characters), acting as a partial sanitizer. `unescape()` is its inverse — it decodes percent-encoded sequences, effectively neutralizing the encoding. Passing tainted input through `unescape()` returns the original unencoded (potentially malicious) string. The pattern tests whether tools distinguish between sanitizing wrappers (`escape`) and their inverses (`unescape`).

**Vulnerable example (Instance 2):**

```javascript
let b = query.name;
res.write(unescape(b));   // XSS — unescape decodes, does NOT sanitize
```

**Language transferable?** Yes — Python's `urllib.parse.unquote()` is the equivalent of `unescape`. C++ uses libcurl's `curl_easy_unescape`. The encode/decode duality is universal.

---

## Transform 46 — Continue Statement

**Pattern:** A labeled `continue loop1` statement skips the rest of the current loop body and proceeds to the next iteration of the labeled outer loop. On the first iteration, `b = 'abcde'` (safe) is written and then `b` is overwritten with `query.name` (tainted); `continue` skips back to the loop condition. On the second iteration, the tainted `b` is written. Tools must model labeled-continue control flow to determine that the second iteration reaches the sink with tainted data.

**Vulnerable example (Instance 1):**

```javascript
var b = 'abcde'; 
var cond = 1;
loop1:
for(let i = 0; i<2; i++){
    res.write(b);
    b = query.name;           // reassign b to tainted value
    if(cond == 1){ 
        cond = 0; 
        continue loop1; 
    }
}   // second iteration: writes tainted b — XSS
```

**Language transferable?** Yes — Python supports `continue` (and labeled loops via flags). C++ supports labeled `continue` with `goto`\-like labels. The control-flow analysis challenge is universal.

---

## Transform 47 — Check Type (typeof)

**Pattern:** `typeof(a) == "string"` returns `true` for any string, including malicious XSS payloads. A developer may use `typeof` as a type guard thinking it provides safety, but it merely confirms the variable is a string — it performs no sanitization. When the guard passes (the input IS a string), the tainted value is written directly to the response.

**Vulnerable example (Instance 1):**

```javascript
var a = query.name;
if(typeof(a) == "string"){
    res.write("string " + a);   // XSS — typeof check confirms it's a string, not safe
}
```

**Language transferable?** Yes — Python uses `isinstance(a, str)` or `type(a) == str`. C++ uses `typeid` or `std::is_same`. The false-safety of a type check without sanitization is universal.

---

## Transform 48 — Compare Variables

**Pattern:** Equality comparisons (`===` strict, `==` loose) may appear to guard against XSS but do not sanitize input. When a tainted string is compared to a safe integer (`a === b` where `b=5`) or a safe string literal (`a == c` where `c="7"`), the comparisons typically evaluate to `false` — but the tainted `a` is still written to the sink inside the conditional branch that is reachable. Tools must determine branch reachability with tainted operands.

**Vulnerable example (Instance 1):**

```javascript
var a = query.name;
var b = 5; var c = "7";
if(a === b){ res.write(a); }   // false for string input (no XSS here)
if(a == c){ res.write(a); }   // true if a == "7"; XSS when condition matches
```

**Language transferable?** Yes — Python distinguishes `==` (value equality) and `is` (identity). C++ has `==` with implicit type coercion in some contexts. Equality-check-as-guard false security is a universal anti-pattern.

---

## Transform 49 — Arrow Function

**Pattern:** Arrow functions (`=>`) implicitly capture `this` from the enclosing scope and support concise body syntax. Here `func = (x) => message = message + x` returns the updated `message` which started as the tainted `query.name`. When `func('safe')` is called, it appends `'safe'` to the already-tainted `message` and returns the result. Tools must model arrow-function closures and their captured outer variables.

**Vulnerable example (Instance 1):**

```javascript
var a = query.name;
message = a;
func = (x) => message = message + x;
res.write(func('safe'));   // XSS — message starts as tainted a; result = a + 'safe'
```

**Language transferable?** Yes — Python lambdas (`lambda x: ...`) capture outer scope. C++ lambdas with `[&]` capture by reference. Arrow-function closure taint is broadly transferable.

---

## Transform 50 — Conditional Assignment (Ternary)

**Pattern:** The ternary operator `condition ? valueIfTrue : valueIfFalse` is a compact conditional assignment. When `x = 5` (which is not `> 9`), the false branch executes: `b = a` (tainted). The tainted value is then written to the sink. Tools must evaluate the condition at analysis time to determine that the tainted branch is always taken when `x = 5`.

**Vulnerable example (Instance 1):**

```javascript
var a = query.name;
var x = 5;
x > 9 ? b = "safe" : b = a;   // x=5, condition false → b = a (tainted)
res.write(b);   // XSS
```

**Language transferable?** Yes — Python ternary: `b = "safe" if x > 9 else a`. C++ ternary: `b = (x > 9) ? "safe" : a`. Ternary-based conditional taint assignment is universal.

---

## Transform 51 — Global Variable

**Pattern:** A `var` declaration at the top-level scope creates a global variable. Function `F(word)` modifies the global `result` by reassigning it to `word` (tainted input). After `F(words)` is called, `result` holds the tainted value and is written to the sink at the global scope. Tools must track that `F` modifies a global variable and that the modified value is later read.

**Vulnerable example (Instance 1):**

```javascript
var result = "I'm global";
function F(word) { result = word; }   // modifies global
var words = query.name;
F(words);
res.write(result);   // XSS — result now holds tainted query.name
```

**Language transferable?** Yes — Python uses the `global` keyword to modify global state from within functions. C++ has global variables modifiable from any function. Global-variable taint propagation is a universal pattern.

---

## Transform 52 — Super Property (Runtime Prototype Addition)

**Pattern:** After class definitions are complete, a property is added to a parent class's prototype at runtime: `first.prototype.add = b`. All instances of both `first` and its child class `second` (which inherits via `extends`) gain this new property through the prototype chain. Accessing `S.add` on a `second` instance retrieves the tainted value. Tools must model runtime prototype mutation and its inheritance effects.

**Vulnerable example (Instance 1):**

```javascript
class first { name = 'super'; }
class second extends first { prop = 'I am second'; }
const b = query.name;
let S = new second();
first.prototype.add = b;   // adds tainted property to parent prototype
res.write(S.add);   // XSS — second inherits 'add' from first's prototype
```

**Language transferable?** Partially — Python allows adding attributes to class objects at runtime (`FirstClass.add = b`), and subclasses inherit them. C++ requires all class members to be declared at compile time; runtime member addition is not possible. Transferable to Python but not C++.

---

## Transform 53 — Simple Set

**Pattern:** A `Set` stores unique values. Tainted user input is added via `mySet.add(b)`. Since Node.js does not support direct `res.write(set)`, the set is serialized using `util.inspect()` which renders the set's contents (including the tainted string) as a string. Tools must track taint through `Set.add()` and understand that `util.inspect()` preserves and exposes the contained values.

**Vulnerable example (Instance 1):**

```javascript
const b = query.name;
let mySet = new Set();
mySet.add(1); 
mySet.add(b); 
mySet.add(2);
const { inspect } = require('util');
res.write(inspect(mySet, { showHidden: true }));   // XSS — inspect serializes b
```

**Language transferable?** Yes — Python has `set` and `repr()`/`str()` serialization. C++ has `std::set` and `std::to_string`/stream operators. The taint-through-collection-serialization pattern is universal.

---

## Transform 54 — Object.defineProperty

**Pattern:** `Object.defineProperty()` defines or modifies a property on an object with a descriptor (including `writable`, `enumerable`, `configurable`). With `writable: true`, the property's value can be updated after definition. The initial safe value is overwritten with tainted input (`obj1.prop1 = b`), and the modified property is written to the sink. Tools must model `defineProperty`\-defined properties as mutable when `writable: true`.

**Vulnerable example (Instance 1):**

```javascript
const b = query.name;
const obj1 = {};
Object.defineProperty(obj1, 'prop1', { value: 'safe', writable: true });
obj1.prop1 = b;   // overwrite safe value with tainted b
res.write(obj1.prop1);   // XSS
```

**Language transferable?** Yes — Python's `@property` decorator with a setter achieves similar behavior. C++ setter methods accomplish the same. Runtime property-descriptor-based assignment is broadly representable.

---

## Transform 55 — Inheritance

**Pattern:** A child class (`secondMyClass`) extends a parent class (`myClass`). The parent's constructor receives and writes the value to the response. When the child class is instantiated with tainted input (`new secondMyClass(b)`), the inherited constructor propagates `b` to the sink. Tools must follow the inheritance chain to identify that the child constructor delegates to the parent's XSS-vulnerable constructor.

**Vulnerable example (Instance 1):**

```javascript
class myClass{
    constructor(val) { 
        res.write(val); 
    }   // XSS in parent constructor
}
class secondMyClass extends myClass{}
b = query.name;
obj = new secondMyClass(b);   // inherits parent constructor — XSS
```

**Language transferable?** Yes — Python class inheritance with `super().__init__()` follows the same pattern. C++ class inheritance with constructor delegation is equivalent. The taint-through-inherited-constructor challenge is universal.

---

## Transform 56 — WeakRef

**Pattern:** A `WeakRef` holds a weak reference to an object, allowing it to be garbage-collected. `c.ref.deref()` returns the referenced object if it has not been collected, or `undefined` otherwise. Tainted input is wrapped in an array `[query.name]` (WeakRef requires an object), stored via `new WeakRef(element)`, and retrieved via `c.ref.deref()[0]`. Tools must track taint through WeakRef storage and deref retrieval.

**Vulnerable example (Instance 1):**

```javascript
class Counter { 
    constructor(element) { 
        this.ref = new WeakRef(element); 
    } 
}
let b = [query.name];   // wrapped in array for WeakRef
let c = new Counter(b);
let v = c.ref.deref();
res.write(v[0]);   // XSS — tainted value retrieved via deref
```

**Language transferable?** Yes — Python has `weakref.ref()` and `.()` deref. C++ has `std::weak_ptr::lock()`. The taint-through-weak-reference-deref pattern is broadly applicable.

---

## Transform 57 — Object Seal

**Pattern:** `Object.seal(obj)` prevents adding new properties and prevents existing properties from being deleted (they become non-configurable). However, values of existing **writable** properties can still be changed. When a tainted value is stored in a property before sealing, `delete obj.property` silently fails (no error in non-strict mode), and the tainted value remains. The subsequent loop outputs the surviving tainted value.

**Vulnerable example (Instance 1):**

```javascript
let b = query.name;
const obj = { property: b };   // tainted value stored
Object.seal(obj);
delete obj.property;   // silently fails — property survives due to seal
for(i in obj){ res.write(obj[i]); }   // XSS — b still present
```

**Language transferable?** No — `Object.seal()` is a JavaScript-specific API. Python and C++ have no direct equivalent mechanism. The concept of "deletion-proof" properties is not directly transferable.

---

## Transform 58 — Object Freeze

**Pattern:** `Object.freeze(obj)` makes an object completely immutable: no property additions, deletions, or value changes are allowed. Tainted data set before freezing is permanently locked in. `delete obj.property` silently fails, preserving the tainted value. Tools must understand that frozen objects still contain (and can still output) tainted data stored before the freeze call.

**Vulnerable example (Instance 1):**

```javascript
let b = query.name;
const obj = { property: b };
Object.freeze(obj);
delete obj.property;   // silently fails — freeze prevents deletion
for(i in obj){ res.write(obj[i]); }   // XSS — b survives freeze
```

**Language transferable?** No — `Object.freeze()` is JavaScript-specific. Python has no equivalent; `frozenset` only applies to sets. C++ `const` objects prevent modification but at compile time. The specific run-time freeze API is JS-only.

---

## Transform 59 — Simple Object (Class Instantiation)

**Pattern:** A class stores user input in `this.foo` via the constructor and exposes it via a `getFoo()` getter method. Instantiating the class with tainted input and calling `getFoo()` returns the tainted value. This is the most basic object-oriented taint propagation: data stored in an instance field flows through a method to the sink. Tools must track taint through object field storage and method-based retrieval.

**Vulnerable example (Instance 1):**

```javascript
class Test{
    constructor(foo) { 
        this.foo = foo; 
    }
    getFoo() { 
        return this.foo; 
    }
}
var b = query.name;
test = new Test(b);
res.write(test.getFoo());   // XSS — getFoo returns tainted this.foo
```

**Language transferable?** Yes — Python classes with `__init__` storing user input and getter methods are identical in structure. C++ class constructors and accessor methods work the same way. This is the most universal OOP taint pattern.

---

## Transform 60 — Object.create

**Pattern:** `Object.create(proto)` creates a new object whose prototype is `proto`. Properties defined on `proto` (including tainted values) are inherited by the created object. Accessing `obj2.name` traverses the prototype chain to find `name` on `obj` (the prototype), returning the tainted value. Tools must model prototype-chain property lookup in `Object.create`\-based inheritance.

**Vulnerable example (Instance 1):**

```javascript
let b = query.name;
const obj = { name: b };
const obj2 = Object.create(obj);   // obj2 inherits from obj
res.write(obj2.name);   // XSS — name lookup traverses prototype chain to obj
```

**Language transferable?** No — `Object.create` is JS-specific feature.

---

## Transform 61 — Delete Properties

**Pattern:** The `delete` operator removes a property from an object. When a class instance has its property deleted, a method that reads `this.property` returns `undefined`. However, if a **copy** of the property value was stored in a separate variable or object before deletion, that copy still holds the tainted value. This pattern involves understanding that deletion of the original does not affect existing copies.

**Vulnerable example (Instance 2):**

```javascript
class myObject{
    constructor(val) { 
        this.property = val; 
        this.property2 = val; 
    }
    out() { 
        res.write('property ' + this.property); 
    }
}
var b = query.name;
var obj = new myObject(b);
delete obj.property;   // deletes property, but property2 still holds tainted b
res.write('property2 ' + obj.property2);   // XSS via surviving copy
```

**Language transferable?** Partially — Python uses `del obj.attr` or `delattr(obj, name)`. C++ lacks property deletion semantics (members are fixed at compile time). Transferable to Python but not C++.

---

## Transform 62 — Static Variable (Class-Level State)

**Pattern:** A `static` class variable is shared across all instances. A method `F(v)` sets `this.variable = v` (which modifies the instance variable, shadowing the static one) when `v != undefined`, or reads `this.variable` when called without arguments. The first call stores the tainted value; the second call retrieves it. Tools must distinguish instance vs. static field semantics and track state across calls.

**Vulnerable example (Instance 1):**

```javascript
class MyClass{
    static variable = 'safe';
    F(v) { 
        if(v != undefined) { 
            this.variable = v; 
        } else { 
            res.write(this.variable); } 
        }
}
var b = query.name;
c = new MyClass();
c.F(b);   // stores tainted b as instance variable
c.F();    // reads this.variable — now tainted — XSS
```

**Language transferable?** Yes — Python class variables (`MyClass.var`) vs. instance variables (`self.var`) have identical semantics. C++ `static` member variables are equivalent. The class-variable taint pattern is universal.

---

## Transform 63 — toString Override

**Pattern:** A class's `toString()` method is overridden on its `prototype` to return a field value. When the instance is converted to a string (e.g., via `f.toString()` or implicit coercion), the overridden method is invoked and returns the tainted field. Tools must model that prototype-level `toString` overrides propagate taint when the instance is converted to a string and passed to a sink.

**Vulnerable example (Instance 1):**

```javascript
class TestClass { 
    constructor(val) { 
        this.foo = val; 
    } 
}
TestClass.prototype.toString = function() { return this.foo; };   // returns tainted foo
b = query.name;
var f = new TestClass(b);
res.write(f.toString());   // XSS — toString returns tainted this.foo
```

**Language transferable?** Yes — Python's `__str__` method is the exact equivalent. C++ uses `operator<<` or a custom `to_string` member. The toString-override taint pattern is universal.

---

## Transform 64 — Assign Object (Reference Semantics)

**Pattern:** In JavaScript, object assignment creates a reference to the same object, not a copy. `obj2 = obj1` means both variables point to the same object. Modifying `obj2.b = query.name` therefore also modifies `obj1.b`. Writing `obj1.b` to the sink outputs the tainted value even though the taint assignment was performed through `obj2`. Tools must understand reference semantics for objects.

**Vulnerable example (Instance 1):**

```javascript
class myClass { b = 'safe'; }
obj1 = new myClass();
obj2 = obj1;          // obj2 and obj1 reference the same object
obj2.b = query.name;  // modifies the shared object
res.write(obj1.b);    // XSS — obj1.b is now tainted via obj2 alias
```

**Language transferable?** Yes — Python objects are references by default; `obj2 = obj1` creates an alias. C++ raw pointers and references have identical aliasing semantics. Reference-based taint aliasing is a universal challenge.

---

## Transform 65 — Proto (Prototype Chain Mutation)

**Pattern:** `__proto__` provides direct access to an object's prototype. Setting `One.prototype.name = b` at runtime and then accessing `t.name` (where `t` is an instance of `Two` whose prototype is set to `new One`) traverses the prototype chain: `Two → One.prototype`. The tainted `name` property is found on `One.prototype` and returned. Tools must model runtime prototype chain mutation to track this taint path.

**Vulnerable example (Instance 1):**

```javascript
function One(){ this.prop = 'one'; }
function Two(){ this.prop2 = 'two'; }
var b = query.name;
One.prototype.name = 'one';
Two.prototype = new One;
var t = new Two;
if(instanceOf(t, Two)){
    One.prototype.name = b;   // modifies prototype property with tainted value
    res.write(t.name);         // XSS — t.name traverses chain to One.prototype.name
}
```

**Language transferable?** Partially — Python supports runtime class attribute modification (`One.name = b`) with the same inheritance effect. C++ does not support runtime prototype chain manipulation. Transferable to Python but not C++.

---

## Transform 66 — Static Methods and Properties

**Pattern:** A class has a `static b = 'safe'` property and an instance property `b` set via the constructor. When `new Foo(b)` is called with tainted input, the **instance** `b` is set to the tainted value (shadowing the static one). The `baz()` method accesses `this.b` (the instance property), which is tainted. Tools must distinguish static vs. instance property resolution and track that `this.b` refers to the instance field, not the static one.

**Vulnerable example (Instance 1):**

```javascript
class Foo{
    static b = 'safe';
    constructor(b) { 
        this.b = b; 
    }  // instance b shadows static b
    baz() { 
        res.write(this.b); 
    }    // reads instance b — XSS
}
var b = query.name;
var obj = new Foo(b);
obj.baz();
```

**Language transferable?** Yes — Python's `@staticmethod`/`@classmethod` vs. instance attributes work the same way. C++ `static` vs. non-static member variables have identical resolution semantics. Universal OOP taint challenge.

---

## Transform 67 — Symbol.toStringTag

**Pattern:** `Symbol.toStringTag` is a well-known symbol that customizes the output of `Object.prototype.toString.call(obj)`. A getter `get [Symbol.toStringTag]()` on a class returns an instance field, which may hold tainted data. When `Object.prototype.toString.call(new MyClass(b))` is invoked, JavaScript appends the `toStringTag` value into the result string `[object <tag>]`. Tools must model this indirect string construction path.

**Vulnerable example (Instance 1):**

```javascript
class MyClass {
    constructor(val){ this.value = val; }
    get [Symbol.toStringTag]() { return this.value; }  // returns tainted field
}
const b = query.name;
res.write(Object.prototype.toString.call(new MyClass(b)));   // XSS via toStringTag
```

**Language transferable?** No — `Symbol.toStringTag` is a JavaScript-specific well-known symbol. Python has `__class__.__name__` and `__repr__`, but the specific `toStringTag` mechanism is JS-only.

---

## Transform 68 — Promise

**Pattern:** `Promise.all([func(b)])` runs promises in parallel and resolves with an array of results. `func(b)` returns a Promise that resolves to `name` (the tainted input). In the `.then()` callback, `values[0]` is the resolved tainted value, which is written to the sink. Tools must track taint through Promise creation, resolution, and `.then()` callback consumption.

**Vulnerable example (Instance 1):**

```javascript
function func(name){
    return new Promise(function(resolve, reject) { 
        resolve(name + ''); 
    });
}
var b = query.name;
Promise.all([func(b)]).then((values) => {
    for(let i=0; i<values.length; i++) { 
        res.write(values[i]); 
    }  // XSS
});
```

**Language transferable?** Yes — Python's `asyncio.gather()` with coroutines is semantically equivalent. C++ has `std::future`/`std::async`. Asynchronous-resolution taint propagation is a broadly applicable challenge.

---

## Transform 69 — Set and Get (Getter/Setter)

**Pattern:** A class defines a `set val(value)` setter that directly writes `value` to the response. When an assignment `obj.val = b` is made with tainted input, JavaScript invokes the setter, which executes `res.write(value)` immediately. Tools must recognize that property assignment syntax triggers a setter method and that the assigned value flows through the setter body to the sink.

**Vulnerable example (Instance 1):**

```javascript
class PropertyTest{
    set val(value) { 
        res.write(value); 
    }  // setter writes directly — XSS
}
b = query.name;
var obj = new PropertyTest;
obj.val = b;   // triggers setter with tainted b
```

**Language transferable?** Yes — Python's `@property` with a setter is semantically identical. C++ uses explicit `set_val(value)` methods (no native property syntax). The setter-triggered taint write is broadly applicable.

---

## Transform 70 — Reflect.get / Reflect.set

**Pattern:** `Reflect.set(target, propertyKey, value)` and `Reflect.get(target, propertyKey)` are reflective object property operations equivalent to assignment and access. Tainted input stored via `Reflect.set` and retrieved via `Reflect.get` passes through the Reflect API to the sink. Tools must model Reflect operations as equivalent to direct property access for taint propagation.

**Vulnerable example (Instance 1):**

```javascript
const b = query.name;
const obj = {};
Reflect.set(obj, 'input', b);          // equivalent to obj.input = b
res.write(Reflect.get(obj, 'input'));   // XSS — retrieves tainted b
```

**Language transferable?** No — the `Reflect` API is JavaScript-specific (part of ES6). Python uses `setattr`/`getattr` for similar reflective property operations. C++ has no built-in reflection. Transferable in concept to Python but not C++.

---

## Transform 71 — Named Class Expression

**Pattern:** A class expression can optionally have an internal name: `const Foo = class NamedFoo {...}`. The external variable `Foo` is used to instantiate the class; the internal name `NamedFoo` is only visible within the class body. Tools must recognize that `new Foo(b)` invokes the named class expression's constructor and that `b` is stored in `this.x`, later written via `printX()`.

**Vulnerable example (Instance 1):**

```javascript
const Foo = class NamedFoo {
    constructor(b){ this.x = b; }
    printX(){ res.write(this.x); }  // XSS — writes stored tainted value
};
var b = query.name;
const bar = new Foo(b);
bar.printX();
```

**Language transferable?** Partially — Python has no named class expressions in the same sense, but equivalent `Foo = type('NamedFoo', (), {'__init__': ..., 'printX': ...})` constructs exist. C++ has no class expressions, only declarations. Partially transferable to Python.

---

## Transform 72 — Errors (Exception Objects)

**Pattern:** A function throws `new Error(val)` with the tainted value as the error message. The caller wraps this in a `try/catch` and writes `err.message` (the tainted value) to the response in the catch block. Tools must track taint through exception object construction (`new Error(tainted)`) to the catch clause and the `err.message` property.

**Vulnerable example (Instance 1):**

```javascript
function F(val){ 
    throw new Error(val); 
}
let b = query.name;
try{ F(b); }
catch(err){
    res.write(err.message);  // XSS — err.message holds tainted b
}
```

**Language transferable?** Yes — Python `raise ValueError(b)` with `except ValueError as e: print(e)` is identical. C++ `throw std::runtime_error(b)` with `catch(std::exception& e) { use(e.what()); }` is equivalent. Exception-based taint propagation is universal.

---

## Transform 73 — WeakSet

**Pattern:** A `WeakSet` stores weakly-referenced objects (must be object types, not primitives). Tainted input is wrapped in an array `[b]` and added to the WeakSet via `ws.add(v)`. The `util.inspect()` function serializes the WeakSet's contents (including the tainted array element) into a string representation that is then written to the response.

**Vulnerable example (Instance 1):**

```javascript
let b = query.name;
let ws = new WeakSet();
const v = [b];   // wrapped in array for WeakSet
ws.add(v);
const { inspect } = require('util');
res.write(inspect(ws, { showHidden: true }));  // XSS — inspect serializes tainted b
```

**Language transferable?** Yes — Python has `weakref.WeakSet()`. C++ can use `std::weak_ptr` collections. The taint-through-weak-collection-serialization pattern is broadly applicable.

---

## Transform 74 — Object Argument (Object Mutation via Parameter)

**Pattern:** An object is passed by reference to a function that modifies its properties. `f(obj1, b)` sets `obj1.prop = b` inside the function body. Since objects are passed by reference in JavaScript, the modification is visible outside the function. Reading `obj1.prop` after the call returns the tainted value. Tools must model that function parameters receiving objects may mutate the caller's object.

**Vulnerable example (Instance 1):**

```javascript
function f(obj, b){ obj.prop = b; }  // mutates caller's object
obj1 = new myClass();
obj1.prop = 'abc';
b = query.name;
f(obj1, b);
res.write(obj1.prop);  // XSS — f mutated obj1.prop to tainted b
```

**Language transferable?** Yes — Python passes objects by reference; mutable object mutation in functions is identical. C++ passes by pointer or reference. Object-mutation-via-parameter taint is a universal challenge.

---

## Transform 75 — Functions in Object

**Pattern:** An object `utils` contains methods stored as properties (`f2`, `f3`). `f2` calls `this.f3(arg1)` and `f3` writes `arg2` to the sink. The outer function `f1(arg)` calls `this.utils.f2(arg)`. Tainted input flows from `f1(a)` → `utils.f2(arg)` → `utils.f3(arg)` → `res.write(arg)`. Tools must resolve method calls on object-valued properties across multiple levels.

**Vulnerable example (Instance 1):**

```javascript
function f1(arg){
    utils = { 
        f2: function(arg1) { 
            this.f3(arg1); 
        }, 
        f3: function(arg2) { 
            res.write(arg2); 
        } 
    };
    this.utils.f2(arg);
}
var a = query.name;
f1(a);  // XSS — a flows through f2 → f3 → write
```

**Language transferable?** Yes — Python dicts with function values and method dispatch are equivalent. C++ structs/objects with function pointer members work the same way. Taint through function-valued object properties is broadly applicable.

---

## Transform 76 — Reference Argument

**Pattern:** JavaScript passes objects by reference, not by value. A function receives an object and a tainted value, then assigns the tainted value to a property of the object: `objA.a = objB`. After the function returns, the caller's object `a` holds the tainted value at `a.a`. Writing `a.a` to the sink creates XSS. Tools must propagate taint from the function's parameter assignment back to the caller's object reference.

**Vulnerable example (Instance 1):**

```javascript
function foo(objA, objB){ objA.a = objB; }  // assigns tainted objB to objA.a
var b = query.name;
a = new myClass();
foo(a, b);
res.write(a.a);  // XSS — a.a was set to tainted b inside foo
```

**Language transferable?** Yes — Python mutable objects passed by reference work identically. C++ uses pointers or references. Pass-by-reference object mutation taint is universal.

---

## Transform 77 — Object Clone (Object.assign)

**Pattern:** `Object.assign(target, source)` copies all enumerable own properties from `source` to `target`, returning `target`. When `source` (`obj1`) was constructed with tainted data, its tainted property `b` is copied to `target` (`obj2`). Calling `obj2.out()` then writes `obj2.b` (the copied tainted value) to the response. Tools must model `Object.assign` as a taint-propagating property copy.

**Vulnerable example (Instance 1):**

```javascript
class myClass{ constructor(val){ this.b = val; } out(){ res.write(this.b); } }
b = query.name;
obj1 = new myClass(b);    // tainted
obj2 = new myClass('');
obj2 = Object.assign(obj2, obj1);  // copies tainted b to obj2
obj2.out();  // XSS — this.b is now tainted
```

**Language transferable?** Yes — Python's `copy.copy()` / `vars(dest).update(vars(src))` achieves shallow object cloning. C++ copy constructors and `std::copy` serve the same purpose. Object-clone taint propagation is universal.

---

## Transform 78 — Asynchronous Event Handler (EventEmitter)

**Pattern:** Node.js's `EventEmitter` allows publish-subscribe style asynchronous event handling. A tainted value is stored as `event.a = a` on the emitter object. A listener callback `func` is registered for the `'build'` event. When `event.emit('build')` fires, `func` is called — it reads `event.a` (tainted) and writes it to the response. Tools must track the taint path across event listener registration and emission.

**Vulnerable example (Instance 1):**

```javascript
var a = query.name;
let event = new events.EventEmitter('build');
event.a = a;                       // tainted value stored on emitter
event.addListener('build', func);
event.emit('build');               // triggers func
function func(){ res.write(event.a); }  // XSS — event.a is tainted
```

**Language transferable?** Partially — Python's `tkinter` and other frameworks have event emitters, and Python's `asyncio` uses callbacks. C++ uses signal/slot patterns (Qt) or callbacks. The event-emission taint pattern is transferable in concept but the specific API is Node.js-specific.

---

## Transform 79 — Inline Function Expression

**Pattern:** A function expression assigned to a variable (`const func = function(x){ return x; }`) is syntactically different from a function declaration but semantically equivalent. Tainted data is passed to `func(a)`, which returns it unchanged to `res.write()`. Tools that differentiate between function declarations and function expressions may handle taint propagation inconsistently between them.

**Vulnerable example (Instance 1):**

```javascript
var a = query.name;
const func = function(x){ return x; };  // inline function expression
res.write(func(a));  // XSS — a flows through inline function
```

**Language transferable?** Yes — Python has `func = lambda x: x` (anonymous) or `def func(x): return x` (named). C++ has `auto func = [](auto x){ return x; }`. Both are equivalent to inline function expressions. Universal pattern.

---

## Transform 80 — JSON (JSON.stringify)

**Pattern:** `JSON.stringify(b)` converts a value to its JSON string representation. For a string input like `query.name`, it returns the quoted string (e.g., `'"<script>..."'`). While this adds quotes, the JSON-stringified content (including any embedded HTML/JavaScript) is written directly to the HTML response and is NOT safely encoded for HTML context. The XSS payload survives inside the JSON string.

**Vulnerable example (Instance 1):**

```javascript
let b = query.name;
res.write(JSON.stringify(b));  // XSS — JSON stringification ≠ HTML encoding
```

**Language transferable?** Yes — Python's `json.dumps()` has the same behavior. C++ JSON libraries (nlohmann/json, rapidjson) produce the same output. The false-sanitization of JSON stringification is a universal pattern.

---

## Transform 81 — TextEncoder (Web API)

**Pattern:** `TextEncoder().encode(string)` converts a string to a `Uint8Array` of UTF-8 encoded bytes. Node.js's `res.write()` accepts both strings and `Buffer`/`Uint8Array` types, writing the byte content directly. A tainted string encoded to a `Uint8Array` and then written to the response effectively sends the original string bytes. The encoding does not sanitize XSS payloads in the HTML context.

**Vulnerable example (Instance 1):**

```javascript
let b = query.name;
const view = new TextEncoder().encode(b);  // Uint8Array of UTF-8 bytes
res.write(view);  // XSS — bytes are sent as-is; HTML context interprets them
```

**Language transferable?** Yes — Python's `b_val = user_input.encode('utf-8')` with `response.write(b_val)` is semantically equivalent. C++ string-to-bytes conversions work similarly. The "encoding as bytes does not sanitize HTML" pattern is universal.

---

## Transform 82 — Location Assign with Search (Client-Side)

**Pattern:** On the client side, `window.location.search` retrieves the query string part of the current URL (e.g., `?name=<payload>`). `location.assign(url)` navigates to the given URL, which may be an attacker-controlled redirect (open redirect or DOM XSS). Tools analyzing client-side JavaScript must model `location.search` as a taint source and `location.assign()` as a sink.

**Vulnerable example (Instance 1):**

```javascript
var location = window.location;
var url = location.search;    // tainted: contains URL query parameters
location.assign(url);         // XSS/open redirect — navigates to attacker-controlled URL
```

**Language transferable?** No — `window.location` and `location.assign()` are browser-specific Web APIs available only in client-side JavaScript. There is no direct equivalent in Python server code or C++.

---

## Transform 83 — getAttribute (Client-Side DOM)

**Pattern:** `element.getAttribute(attrName)` retrieves an HTML attribute value from a DOM element. If the attribute value is user-influenced (e.g., set server-side from user input), reading it and passing it to `document.write()` creates a DOM-based XSS. Tools must model `getAttribute` as a potential taint source when the attribute originates from user data.

**Vulnerable example (Instance 1):**

```javascript
var content = document.getElementsByTagName("DIV")[0].getAttribute('data_type');
document.write(content);  // XSS — attribute value may contain attacker-controlled data
```

**Language transferable?** No — `document.getElementsByTagName()`, `getAttribute()`, and `document.write()` are browser DOM APIs available only in client-side JavaScript. Not applicable to Python or C++.

---

## Transform 84 — Try Catch

**Pattern:** A `try/catch` block catches exceptions thrown during execution. Tainted input `b_to_func` is used both inside the try block (as an argument to `inverse`) and directly written in the catch block. The catch block runs when `inverse(0, b_to_func)` throws (since division by zero is an error in this context). The tainted `b_to_func` is then written to the response. Tools must track taint across try/catch block boundaries.

**Vulnerable example (Instance 1):**

```javascript
var b_to_func = query.name;
try{
    inverse(5, b_to_func);
    inverse(0, b_to_func);   // throws
}catch(err){
    res.write(b_to_func);  // XSS — tainted variable in catch scope
}
```

**Language transferable?** Yes — Python `try/except` blocks work identically. C++ `try/catch` is semantically equivalent. Try-catch taint propagation is universal.

---

## Transform 85 — Block Scope (let/const)

**Pattern:** `let` and `const` declarations are block-scoped. A `let b = query.name` declared in the outer scope remains accessible after an inner block that declares a **different** `let b = 'hi'`. The inner block's `b` shadows the outer one only within the block; after the block, the outer tainted `b` is back in scope. Writing `b` after the inner block outputs the tainted outer value. Tools must correctly model `let`/`const` block-scope shadowing.

**Vulnerable example (Instance 1):**

```javascript
let b = query.name;  // outer scope — tainted
{
    let b = 'hi';    // inner block — shadows outer b within this block only
}
res.write(b);  // XSS — outer b is still tainted; inner b is out of scope
```

**Language transferable?** Yes — Python has function-level scope (not block scope), so the behavior differs slightly, but the variable-shadowing concept applies. One example is:

```py
a = 1000
(lambda i: (a := i))(10)
print(a)
```

C++ has block scope identical to JavaScript's `let`. The block-scope-shadowing taint challenge is broadly applicable.

---

## Transform 86 — Type Juggling (Character-Level String Manipulation)

**Pattern:** The code iterates over each character of a string `stringa` using `charCodeAt(i)` to get its ASCII value, then `String.fromCharCode(od)` to reconstruct it (after adding 1 and subtracting 1, for a net zero change). The result is a character-by-character reconstruction of the input string, which is then written to the response. SAST tools must recognize that the loop reconstructs the original tainted string unchanged.

**Vulnerable example (Instance 1):**

```javascript
var number = query.name1;  var stringa = query.name2;
var result = '';
for(let i = 0; i<number; i++){
    var od = stringa.charCodeAt(i) + 1;
    od = od - 1;
    result = result.concat(String.fromCharCode(od));  // reconstruct original char
}
res.write(result);  // XSS — result === stringa (tainted)
```

**Language transferable?** Yes — Python's `chr(ord(c) + 1 - 1)` is equivalent. C++ has identical character arithmetic with `char`. Character-level string reconstruction as an obfuscation pattern is universal.

---

## Transform 87 — Modules (CommonJS require/exports)

**Pattern:** Node.js CommonJS modules split code across files. A module (`b.js`) exports `assign` and `get` functions. The main server requires the module and calls `modules.assign(b)` to store tainted input in the module's internal state, then `modules.get()` to retrieve it. SAST tools performing single-file analysis miss the inter-module taint flow; multi-file analysis must track that `assign` stores to and `get` reads from shared module state.

**Vulnerable example (Instance 1):**

```javascript
// modules/b.js
module.exports = {
    assign: function(val){ this.b_in_modules = val; },
    get: function(){ return this.b_in_modules; }
};
// server.js
var modules = require('./modules/b');
var b = query.name;
modules.assign(b);
res.write(modules.get());  // XSS — taint flows through module boundary
```

**Language transferable?** Partially — Python's `import` with module-level state achieves the same effect. C++ has no equivalent module-state pattern (static global variables in translation units are closest). The cross-module taint pattern is transferable to Python.

---

---

## Transform 89 — Proxy

**Pattern:** A `Proxy` object intercepts property operations via a handler. The `defineProperty` trap stores the descriptor object under the key; `get` returns `target[name]` directly. When `p.b = b` is executed, the `defineProperty` trap is triggered and stores the descriptor `{value: b, ...}` (the descriptor passed for property assignment) under key `'b'`. Accessing `p.b` then returns that descriptor object, and `.value` yields the tainted string.

**Vulnerable example (Instance 1):**

```javascript
var handler = {
    defineProperty(target, key, descriptor){ return prop(key, 'define', target, descriptor); },
    get: function(target, name){ return name in target ? target[name] : 'proxy prop not defined'; }
};
function prop(key, action, target, descriptor){
    if(action === 'define'){ target[key] = descriptor; return true; }
}
var b = query.name;
let p = new Proxy({}, handler);
p.b = b;
res.write(p.b.value);  // XSS — taint stored via defineProperty trap
```

**Language transferable?** No — `Proxy` is a JavaScript-specific API for meta-object programming. Python has `__getattr__`/`__setattr__` magic methods for similar interception. C++ has no direct runtime interception mechanism. Partially transferable to Python.

---

## Transform 90 — Simple Array

**Pattern:** A simple array literal contains a mix of safe string values and a tainted value at a known index. Directly accessing the tainted element by its index and writing it to the response creates XSS. This is the most fundamental array-based taint pattern: user input placed at `array[2]` is written via `res.write(array[2])`.

**Vulnerable example (Instance 1):**

```javascript
var a = query.name;
var array = ['a', 'b', a, 'c'];
res.write(array[2]);  // XSS — array[2] is the tainted input
```

**Language transferable?** Yes — Python lists and C++ vectors/arrays have identical indexed-access semantics. This is the simplest and most universal array taint pattern.

---

## Transform 91 — Destructuring Assignment

**Pattern:** Array destructuring `[one, two, three] = vect` assigns array elements to named variables positionally. Tainted input placed at index 1 of the array is assigned to `two`. Writing all three destructured variables to the response causes XSS via `two`. Tools must model that destructuring preserves taint from the array element to the corresponding named variable.

**Vulnerable example (Instance 1):**

```javascript
var second = query.name;
var vect = ['first', second, 'third'];
var [one, two, three] = vect;  // two = second (tainted)
res.write(one); res.write(two); res.write(three);  // XSS via two
```

**Language transferable?** Yes — Python tuple unpacking `(one, two, three) = vect` is semantically identical. C++ uses `std::tie` or structured bindings (C++17). Destructuring-based taint is a broadly transferable concept.

---

## Transform 92 — Set to Array Conversion

**Pattern:** A `Set` (which eliminates duplicates) is converted to an array using the spread operator `[...set]`. Tainted input added to the set (twice, but deduplicated to once) survives in the resulting array. The `while` loop iterates over the array and writes each element to the response, including the tainted one. Tools must track taint through `Set → spread → array → loop → sink`.

**Vulnerable example (Instance 2):**

```javascript
var b = query.name;
var set = new Set();
set.add('first'); 
set.add('second'); 
set.add(b); 
set.add(b);  // b added twice, stored once
array = [...set];   // b present in array (not removed)
while(array[i] != undefined){ res.write(array[i]); i++; }  // XSS
```

**Language transferable?** Yes — Python `list(set_var)` converts a set to a list; tainted elements survive. C++ `std::vector(set.begin(), set.end())` copies set elements. The set-to-collection-conversion taint pattern is universal.

---

## Transform 93 — For...Of Loop

**Pattern:** The `for...of` statement iterates over iterable objects (arrays, sets, strings, etc.), binding each element to the loop variable. Tainted input placed inside an array is iterated and each value (including the tainted one) is written to the sink. Tools must model that `for...of` iterates all elements and that taint in any element reaches the sink body.

**Vulnerable example (Instance 1):**

```javascript
let b = query.name;
let array = ['1', 'two', b];
for(let i of array){
    res.write(i);  // XSS — tainted b is one of the iterated values
}
```

**Language transferable?** Yes — Python's `for item in iterable` is semantically identical. C++ range-based `for(auto i : array)` is equivalent. For-each iteration taint is a universal pattern.

---

## Transform 94 — Matrix (Multi-Dimensional Array)

**Pattern:** A 2D array (matrix) is created as an array of arrays: `a[i] = new Array(3)`. Tainted input is stored at position `[0][0]`. Direct access `a[0][0]` retrieves and writes the tainted value to the sink. Tools must track taint through nested array (matrix) indexing, following the path `query.name → a[0][0] → res.write()`.

**Vulnerable example (Instance 1):**

```javascript
const b = query.name;
let a = new Array(3);
for(let i = 0; i<3; i++) { 
    a[i] = new Array(3);
}
a[0][0] = b;
res.write(a[0][0]);  // XSS — nested array element is tainted
```

**Language transferable?** Yes — Python nested lists `a[0][0] = user_input` are identical. C++ 2D arrays `a[0][0] = b` work the same way. Nested-array taint is a universal challenge.

---

## Transform 95 — Arithmetic Operation on Array Index

**Pattern:** The array index used to access a tainted element is computed via arithmetic (`index = 3; index = index - 1`), resulting in `index = 2`. The element at `array[index]` is the tainted value `c`. Tools must evaluate or over-approximate the arithmetic expression to determine which array position is accessed, and whether a tainted element resides there.

**Vulnerable example (Instance 1):**

```javascript
var c = query.name;
array = ['a', 'b', c, 'd'];
index = 3;
index = index - 1;  // evaluates to 2
res.write(array[index]);  // XSS — array[2] is tainted c
```

**Language transferable?** Yes — Python `array[3-1]` and C++ `array[3-1]` are identical. Arithmetic-expression-based array index taint analysis is a universal static analysis challenge.

---

## Transform 96 — Object Literals

**Pattern:** An object literal is initialized with a mix of safe and tainted property values: `{first: 'first', second: types(b), third: p}`. The function `types(b)` returns either `b` or `b + ' not present'` (both tainted). Accessing `values.second` and writing it creates XSS. Tools must trace taint through function calls used as object literal property initializers.

**Vulnerable example (Instance 1):**

```javascript
function types(val){ 
    if(val == 'safe') { 
        return val; 
    } else { 
        return val + ' not present'; 
    } 
}
var b = query.name;
var values = {first: 'first', second: types(b), third: p};
res.write(values.second);  // XSS — types(b) returns tainted b
```

**Language transferable?** Yes — Python dict literals `{'second': types(b)}` are identical. C++ `std::map` or struct initialization with function-call expressions is equivalent. Object-literal taint propagation is universal.

---

## Transform 97 — Vulnerable Key Dictionary

**Pattern:** User-controlled input is used as a **dictionary key** rather than a value: `dictionary[a] = 10`. When the `for...in` loop iterates over the dictionary's keys and writes `i.toString()` (the key name), it outputs the tainted key (which is `query.name`). This is key-injection XSS: the attacker controls a property name that is later serialized and sent to the response.

**Vulnerable example (Instance 1):**

```javascript
var a = query.name;
var dictionary = { foo: 'foo', 'doo': 'doo', 10: 100 };
dictionary[a] = 10;  // adds entry with tainted key
for(var i in dictionary){
    res.write(i.toString());  // XSS — i is the tainted key 'a'
}
```

**Language transferable?** Yes — Python `dict[user_input] = value` followed by `for k in dict: print(k)` is identical. C++ `map[user_input] = value` with key iteration is equivalent. Key-injection taint is a broadly applicable and often overlooked pattern.

---

## Transform 98 — Throw Exception

**Pattern:** A function `inverse` throws `new Error(b)` (with the tainted value as the error message) when its first argument is falsy. The `try` block calls `inverse(0, b_to_func)`, which triggers the throw. The `catch` block writes `err.message` — which is the tainted value — to the response. Unlike Transform 84 (where the tainted variable is written directly), here the taint flows through the Error object's `message` property.

**Vulnerable example (Instance 1):**

```javascript
function inverse(x, b) { 
    if(!x) { 
        throw new Error(b); 
    } 
    return 1/x; 
}
var b_to_func = query.name;
try { 
    inverse(5, b_to_func); 
    inverse(0, b_to_func); 
}
catch(err){
    res.write("Exception " + err.message);  // XSS — err.message is tainted b
}
```

**Language transferable?** Yes — Python `raise ValueError(user_input)` with `except ValueError as e: print(str(e))` is identical. C++ `throw std::runtime_error(b)` with `e.what()` is equivalent. Exception-message taint is universal.

---

## Transform 100 — Replace Substring

**Pattern:** `String.prototype.replace(searchValue, newValue)` replaces the **first** occurrence of `searchValue` with `newValue`. When tainted user input is the replacement value (`a`), the resulting string contains the tainted payload embedded at the position of the first match. The resulting string is then written to the response. Tools must track that the second argument of `replace()` propagates taint into the return value.

**Vulnerable example (Instance 1):**

```javascript
var a = query.name;
const p = 'The quick brown fox jumps over the lazy dog. If the dog reacted, was it really lazy?';
res.write(p.replace('dog', a));  // XSS — a is substituted into p at first 'dog'
```

**Language transferable?** Yes — Python `str.replace(old, new)` is semantically identical. C++ `std::string::replace()` and `boost::regex_replace()` are equivalent. String-replacement taint is a universal pattern.

---

