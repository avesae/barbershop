// Сборка статики: HTML/JS из src, шрифты из npm, CSS через Tailwind CLI.
// STATIC_DEMO=1 — витрина без сервера (Vercel): API заменяет js/demo-api.js.
import { execFileSync } from "node:child_process";
import { cpSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const STATIC = process.env.STATIC_DEMO === "1";
const out = STATIC ? "dist-static" : "dist";

rmSync(out, { recursive: true, force: true });
cpSync("src", out, {
  recursive: true,
  filter: (p) => !p.includes("/css") && (STATIC || !p.endsWith("demo-api.js")),
});
mkdirSync(`${out}/assets/fonts`, { recursive: true });
for (const family of ["unbounded", "manrope"]) {
  for (const subset of ["latin", "cyrillic"]) {
    const file = `${family}-${subset}-wght-normal.woff2`;
    cpSync(`node_modules/@fontsource-variable/${family}/files/${file}`, `${out}/assets/fonts/${file}`);
  }
}
execFileSync("node_modules/.bin/tailwindcss", ["-i", "src/css/app.css", "-o", `${out}/assets/app.css`, "--minify"], {
  stdio: "inherit",
});

if (STATIC) {
  // demo-api.js должен выполниться раньше всех скриптов страницы.
  const walk = (dir) => readdirSync(dir).flatMap((f) => (statSync(join(dir, f)).isDirectory() ? walk(join(dir, f)) : [join(dir, f)]));
  for (const file of walk(out).filter((f) => f.endsWith(".html"))) {
    const html = readFileSync(file, "utf8");
    writeFileSync(file, html.replace("</head>", '  <script src="/js/demo-api.js"></script>\n</head>'));
  }
}
