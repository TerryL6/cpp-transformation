# cpp_transform report

Total records: 20

## Status by transform

- `macro_alias`: skipped=7, success=3
- `variable_chain`: skipped=6, success=4

## srcML reparse

n/a=13, passed=7

## Source locations

tab_size (run-level): 8

Records with a captured before-location: 7/20; with an after-location: 7/20

- relative_to (before): input=7

## Samples

### Sample 1: `macro_alias` on `func_vuln` -> skipped
_note: no_candidates_

```diff
(no change)
```

### Sample 2: `variable_chain` on `func_vuln` -> success

```diff
--- variable_chain (original)
+++ variable_chain (transformed)
@@ -7,7 +7,7 @@
   int av_length, av_readonly;
   MYSQL_ROW cols;
   D_imp_dbh_from_sth;
-  MYSQL* svsock= imp_dbh->pmysql;
+  MYSQL* __chain_svsock = imp_dbh->pmysql; MYSQL* svsock = __chain_svsock;
   imp_sth_fbh_t *fbh;
   D_imp_xxh(sth);
 #if MYSQL_VERSION_ID >=SERVER_PREPARE_VERSION
@@ -123,7 +123,7 @@
          buffer++
         )
     {
-      SV *sv= AvARRAY(av)[i]; /* Note: we (re)use the SV in the AV	*/
+      SV * __chain_sv = AvARRAY(av)[i]; SV * sv = __chain_sv; /* Note: we (re)use the SV in the AV	*/
       STRLEN len;
 
       /* This is wrong, null is not being set correctly
@@ -150,8 +150,8 @@
 
           if (DBIc_TRACE_LEVEL(imp_xxh) >= 2) {
             int j;
-            int m = MIN(*buffer->length, buffer->buffer_length);
-            char *ptr = (char*)buffer->buffer;
+            int __chain_m = MIN(*buffer->length, buffer->buffer_length); int m = __chain_m;
+            char * __chain_ptr = (char*)buffer->buffer; char * ptr = __chain_ptr;
             PerlIO_printf(DBIc_LOGPIO(imp_xxh),"\t\tbefore buffer->buffer: ");
             for (j = 0; j < m; j++) {
               PerlIO_printf(DBIc_LOGPIO(imp_xxh), "%c", *ptr++);
@@ -167,8 +167,8 @@
 
           if (DBIc_TRACE_LEVEL(imp_xxh) >= 2) {
             int j;
-            int m = MIN(*buffer->length, buffer->buffer_length);
-            char *ptr = (char*)buffer->buffer;
+            int __chain_m_1 = MIN(*buffer->length, buffer->buffer_length); int m = __chain_m_1;
+            char * __chain_ptr_1 = (char*)buffer->buffer; char * ptr = __chain_ptr_1;
             PerlIO_printf(DBIc_LOGPIO(imp_xxh),"\t\tafter buffer->buffer: ");
             for (j = 0; j < m; j++) {
               PerlIO_printf(DBIc_LOGPIO(imp_xxh), "%c", *ptr++);
@@ -327,8 +327,8 @@
 
     for (i= 0;  i < num_fields; ++i)
     {
-      char *col= cols[i];
-      SV *sv= AvARRAY(av)[i]; /* Note: we (re)use the SV in the AV	*/
+      char * __chain_col = cols[i]; char * col = __chain_col;
+      SV * __chain_sv_1 = AvARRAY(av)[i]; SV * sv = __chain_sv_1; /* Note: we (re)use the SV in the AV	*/
 
       if (col)
       {
```

### Sample 3: `macro_alias` on `func_vuln` -> skipped
_note: no_candidates_

```diff
(no change)
```

### Sample 4: `variable_chain` on `func_vuln` -> success

```diff
--- variable_chain (original)
+++ variable_chain (transformed)
@@ -2,9 +2,9 @@
                                                       void *dummy,
                                                       const char *arg)
 {
-    const char *endp = ap_strrchr_c(arg, '>');
+    const char * __chain_endp = ap_strrchr_c(arg, '>'); const char * endp = __chain_endp;
     const char *limited_methods;
-    void *tog = cmd->cmd->cmd_data;
+    void * __chain_tog = cmd->cmd->cmd_data; void * tog = __chain_tog;
     apr_int64_t limited = 0;
     apr_int64_t old_limited = cmd->limited;
     const char *errmsg;
@@ -20,7 +20,7 @@
     }
 
     while (limited_methods[0]) {
-        char *method = ap_getword_conf(cmd->temp_pool, &limited_methods);
+        char * __chain_method = ap_getword_conf(cmd->temp_pool, &limited_methods); char * method = __chain_method;
         int methnum;
 
         /* check for builtin or module registered method number */
```

### Sample 5: `macro_alias` on `func_vuln` -> success

```diff
--- macro_alias (original)
+++ macro_alias (transformed)
@@ -1,3 +1,4 @@
+#define SAFE_FREE free
 int wwunpack(uint8_t *exe, uint32_t exesz, uint8_t *wwsect, struct cli_exe_section *sects, uint16_t scount, uint32_t pe, int desc) {
   uint8_t *structs = wwsect + 0x2a1, *compd, *ccur, *unpd, *ucur, bc;
   uint32_t src, srcend, szd, bt, bits;
@@ -138,7 +139,7 @@
 	ucur++;
       }
     }
-    free(compd);
+    SAFE_FREE(compd);
     if(error) {
       cli_dbgmsg("WWPack: decompression error\n");
       break;
@@ -178,3 +179,4 @@
   }
   return error;
 }
+#undef SAFE_FREE
```

### Sample 6: `variable_chain` on `func_vuln` -> skipped
_note: no_candidates_

```diff
(no change)
```

### Sample 7: `macro_alias` on `func_vuln` -> skipped
_note: no_candidates_

```diff
(no change)
```

### Sample 8: `variable_chain` on `func_vuln` -> skipped
_note: no_candidates_

```diff
(no change)
```

### Sample 9: `macro_alias` on `func_vuln` -> success

```diff
--- macro_alias (original)
+++ macro_alias (transformed)
@@ -1,3 +1,6 @@
+#define SAFE_FREE free
+#define SAFE_FREE_1 free
+#define SAFE_FREE_2 free
 int shadow_server_start(rdpShadowServer* server)
 {
 	BOOL ipc;
@@ -43,7 +46,7 @@
 		char** list = CommandLineParseCommaSeparatedValuesEx(NULL, server->ipcSocket, &count);
 		if (!list || (count <= 1))
 		{
-			free(list);
+			SAFE_FREE(list);
 			if (server->ipcSocket == NULL)
 			{
 				if (!open_port(server, NULL))
@@ -58,11 +61,11 @@
 			BOOL success = open_port(server, list[x]);
 			if (!success)
 			{
-				free(list);
+				SAFE_FREE_1(list);
 				return -1;
 			}
 		}
-		free(list);
+		SAFE_FREE_2(list);
 	}
 	else
 	{
@@ -82,3 +85,6 @@
 
 	return 0;
 }
+#undef SAFE_FREE_2
+#undef SAFE_FREE_1
+#undef SAFE_FREE
```

### Sample 10: `variable_chain` on `func_vuln` -> success

```diff
--- variable_chain (original)
+++ variable_chain (transformed)
@@ -40,7 +40,7 @@
 	if (!ipc)
 	{
 		size_t x, count;
-		char** list = CommandLineParseCommaSeparatedValuesEx(NULL, server->ipcSocket, &count);
+		char** __chain_list = CommandLineParseCommaSeparatedValuesEx(NULL, server->ipcSocket, &count); char** list = __chain_list;
 		if (!list || (count <= 1))
 		{
 			free(list);
```
