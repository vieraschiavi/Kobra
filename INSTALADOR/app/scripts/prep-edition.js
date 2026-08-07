#!/usr/bin/env node
// Genera resources/build-config.json y fija el nombre de producto/artefacto
// según la edición pedida ("cliente" u "owner"), antes de invocar
// electron-builder. Correr en Windows (o CI Windows) junto con
// scripts/build-cliente.* / build-owner.* — ver INSTALADOR/README.md.

const fs = require("fs");
const path = require("path");

const edicion = process.argv[2];
if (!["cliente", "owner"].includes(edicion)) {
  console.error('Uso: node prep-edition.js <cliente|owner>');
  process.exit(1);
}

const resourcesDir = path.join(__dirname, "..", "resources");
fs.mkdirSync(resourcesDir, { recursive: true });
fs.writeFileSync(
  path.join(resourcesDir, "build-config.json"),
  JSON.stringify({ edition: edicion }, null, 2)
);

// electron-builder.yml lee esta variable para el nombre del instalador
// (ver ${env.KOBRA_ARTIFACT_SUFFIX} en electron-builder.yml).
process.env.KOBRA_ARTIFACT_SUFFIX = edicion;
fs.writeFileSync(
  path.join(__dirname, "..", ".edition-env"),
  `KOBRA_ARTIFACT_SUFFIX=${edicion}\n`
);

console.log(`✔ Preparado build-config.json para la edición "${edicion}"`);
console.log("  Recordá: kobra-api.exe (PyInstaller) debe estar en resources/kobra-api/ antes de empaquetar.");
