// MapLibre 6 module workers must keep their sibling shared-module import.
// Generate public assets from the exact locked dependency, never from a CDN.
import { copyFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
const root = new URL("../", import.meta.url);
const target = new URL("public/vendor/maplibre/", root);
mkdirSync(target, { recursive: true });
for (const name of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(new URL(`node_modules/maplibre-gl/dist/${name}`, root), new URL(name, target));
}
copyFileSync(new URL("node_modules/maplibre-gl/LICENSE.txt", root), new URL("LICENSE.txt", target));
console.log(`Prepared local MapLibre workers: ${fileURLToPath(target)}`);
