# cpp_transform report

Total records: 1

## Status by transform

- `variable_chain`: success=1

## srcML reparse

passed=1

## Repository validation

passed=1

## Source locations

tab_size (run-level): 8

Records with a captured before-location: 1/1; with an after-location: 1/1

- relative_to (before): input=1

## Samples

### Sample 1: `variable_chain` on `func_vuln` -> success

```diff
--- variable_chain (original)
+++ variable_chain (transformed)
@@ -1,7 +1,7 @@
 static int rm_read_multi(AVFormatContext *s, AVIOContext *pb,
                          AVStream *st, char *mime)
 {
-    int number_of_streams = avio_rb16(pb);
+    int __chain_number_of_streams = avio_rb16(pb); int number_of_streams = __chain_number_of_streams;
     int number_of_mdpr;
     int i, ret;
     unsigned size2;
```
