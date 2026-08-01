# Librerías de terceros vendorizadas

Este dashboard se abre con doble clic (`file://`) y también se sirve tal cual
por HTTP: no hay build step ni CDN de por medio, así que las librerías que usa
están copiadas a mano en esta carpeta en vez de instaladas por npm. Eso las
saca del árbol de dependencias que actualiza `npm audit` — por eso quedan
declaradas acá, con versión y estado de CVEs conocidos, para que "no está en
`package.json`" no signifique "nadie sabe qué hay adentro".

| Archivo | Librería | Versión | Origen | CVE conocido | Estado en este repo |
|---|---|---|---|---|---|
| `chart.umd.min.js` | [Chart.js](https://www.chartjs.org/) | 4.4.1 | jsDelivr (`/npm/chart.js@4.4.1/dist/chart.umd.js`) | Ninguno encontrado para 4.x | — |
| `xlsx.full.min.js` | [SheetJS Community Edition](https://sheetjs.com/) | **0.19.3** (actualizado desde 0.18.5) | `cdn.sheetjs.com` — la 0.19.3 corrige el CVE de abajo pero **nunca se publicó en npmjs.org** (la última ahí es 0.18.5), por eso no alcanza con `npm install xlsx` | [CVE-2023-30533](https://nvd.nist.gov/vuln/detail/CVE-2023-30533) (CVSS 7.8, prototype pollution vía archivo `.xlsx` armado a mano) afecta a **todo ≤0.19.2**, incluida la 0.18.5 que estaba vendorizada acá | **Corregido** — ver nota abajo |
| `botid-init.js` (acá y en `landing/`) | [Vercel BotID](https://vercel.com/docs/botid) | ~1.5.11 (paquete `botid`, resuelto en `package-lock.json` de la raíz) | Bundle generado con esbuild — ver el comentario de cabecera del propio archivo | — | Versión fijada por `package.json`/`package-lock.json`, sí entra en `npm audit` |

## Sobre el CVE de SheetJS — por qué importaba igual estando en 0.18.5

El CVE necesita que la aplicación **parsee** (`XLSX.read` / `XLSX.readFile`)
un archivo `.xlsx` armado por un atacante. Antes de actualizar se verificó con
un grep sobre el código propio:

```
$ grep -rn "XLSX\." dashboard_estatico/index.html landing/*.html
dashboard_estatico/index.html:432:  const wb=XLSX.utils.book_new();
dashboard_estatico/index.html:433:  XLSX.utils.book_append_sheet(wb,XLSX.utils.json_to_sheet(exportRows()),'Cartera');
dashboard_estatico/index.html:434:  XLSX.writeFile(wb,'kobra_cartera.xlsx');
dashboard_estatico/index.html:734:  var wb=XLSX.utils.book_new();
dashboard_estatico/index.html:735:  XLSX.utils.book_append_sheet(wb,XLSX.utils.json_to_sheet(RESULTADOS),'Resultados');
dashboard_estatico/index.html:736:  XLSX.writeFile(wb,'kobra_resultados_erp.xlsx');

$ grep -rln "XLSX.read\b\|XLSX.readFile" --include=*.html --include=*.js .
(sin resultados fuera del propio archivo vendorizado)
```

O sea: acá SheetJS solo **escribe** `.xlsx` a partir de datos que genera la
propia página — nunca lee un archivo que suba alguien. La ruta vulnerable
(parsear un `.xlsx` ajeno) no se invocaba nunca, así que el riesgo real era
bajo. Se actualizó igual a 0.19.3, verificado en Chromium (el botón "Exportar
Excel" sigue produciendo un `.xlsx` válido — firma ZIP `PK` correcta), porque
"sin riesgo hoy" no es lo mismo que "sin riesgo si alguien agrega mañana un
`XLSX.read` para importar cartera" — y a esta altura ya no cuesta nada tenerla
corregida.

## Cómo actualizar

- **Chart.js**: `https://cdn.jsdelivr.net/npm/chart.js@<version>/dist/chart.umd.min.js`
- **SheetJS**: `https://cdn.sheetjs.com/xlsx-<version>/package/dist/xlsx.full.min.js`
  (no usar npm — la build corregida no está publicada ahí)
- **botid**: `npm install` en la raíz y regenerar el bundle (ver el comentario
  de cabecera de `botid-init.js` para el comando exacto)

Después de cualquier actualización, correr `tests/test_scoring_web.py` y
verificar a mano que "Exportar Excel" siga descargando un archivo válido — es
la única forma de confirmar que la API pública de la librería no cambió.
