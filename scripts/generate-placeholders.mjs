// Генерує локальні SVG-заглушки для товарів і категорій у public/images.
// Запуск: node scripts/generate-placeholders.mjs
// Ілюстрації складаються з «цеглинок» і не використовують чужих зображень.
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const OUT_PRODUCTS = path.join("public", "images", "products");
const OUT_CATEGORIES = path.join("public", "images", "categories");
mkdirSync(OUT_PRODUCTS, { recursive: true });
mkdirSync(OUT_CATEGORIES, { recursive: true });

const shade = (hex, amt) => {
  const n = parseInt(hex.slice(1), 16);
  const c = (v) => Math.max(0, Math.min(255, v + amt));
  const r = c(n >> 16), g = c((n >> 8) & 255), b = c(n & 255);
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
};

/** Цеглинка з «пупирцями» зверху. */
function brick(x, y, w, h, color, studs = true) {
  const parts = [
    `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6" fill="${color}"/>`,
    `<rect x="${x}" y="${y + h - 8}" width="${w}" height="8" rx="4" fill="${shade(color, -40)}"/>`,
  ];
  if (studs) {
    const count = Math.max(1, Math.round(w / 40));
    const step = w / count;
    for (let i = 0; i < count; i++) {
      const sx = x + step * i + step / 2 - 12;
      parts.push(`<rect x="${sx}" y="${y - 10}" width="24" height="12" rx="4" fill="${shade(color, 25)}"/>`);
    }
  }
  return parts.join("");
}

const window_ = (x, y, w = 40, h = 40) =>
  `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="4" fill="#cfeaff" stroke="#2b3a55" stroke-width="4"/>`;
const wheel = (cx, cy, r = 34) =>
  `<circle cx="${cx}" cy="${cy}" r="${r}" fill="#222"/><circle cx="${cx}" cy="${cy}" r="${r / 2.3}" fill="#bbb"/>`;

const scenes = {
  city: (c) =>
    brick(220, 560, 360, 60, c[0]) + brick(240, 480, 320, 80, c[1]) + brick(240, 400, 320, 80, c[1]) +
    brick(240, 320, 320, 80, c[1]) + brick(280, 260, 240, 60, c[0]) +
    window_(270, 420) + window_(340, 420) + window_(420, 420) + window_(490, 420) +
    window_(270, 340) + window_(340, 340) + window_(420, 340) + window_(490, 340) +
    `<rect x="370" y="500" width="60" height="60" rx="4" fill="#2b3a55"/>`,
  car: (c) =>
    brick(180, 440, 440, 80, c[0]) + brick(280, 360, 220, 80, c[1]) + window_(300, 375, 80, 40) +
    window_(400, 375, 80, 40) + wheel(270, 530) + wheel(530, 530) +
    `<rect x="590" y="460" width="24" height="18" rx="4" fill="#ffe17a"/>`,
  rocket: (c) =>
    `<polygon points="400,150 470,280 330,280" fill="${c[0]}"/>` + brick(330, 280, 140, 80, c[1], false) +
    brick(330, 360, 140, 80, c[1], false) + brick(330, 440, 140, 80, c[1], false) +
    `<circle cx="400" cy="340" r="30" fill="#cfeaff" stroke="#2b3a55" stroke-width="6"/>` +
    `<polygon points="330,440 270,560 330,520" fill="${c[0]}"/><polygon points="470,440 530,560 470,520" fill="${c[0]}"/>` +
    `<polygon points="360,520 440,520 400,640" fill="#ff9f1c"/><polygon points="380,520 420,520 400,590" fill="#ffe17a"/>`,
  castle: (c) =>
    brick(200, 520, 400, 80, c[0]) + brick(200, 440, 400, 80, c[0]) + brick(200, 360, 100, 80, c[1]) +
    brick(500, 360, 100, 80, c[1]) + brick(200, 280, 100, 80, c[1]) + brick(500, 280, 100, 80, c[1]) +
    brick(340, 380, 120, 60, c[1]) +
    `<path d="M360 600 v-70 a40 40 0 0 1 80 0 v70z" fill="#5a3b1e"/>` +
    `<rect x="245" y="200" width="6" height="80" fill="#333"/><polygon points="251,200 300,220 251,240" fill="${c[2]}"/>`,
  technic: (c) => {
    let g = "";
    const cx = 400, cy = 380, teeth = 12;
    for (let i = 0; i < teeth; i++) {
      const a = (i / teeth) * Math.PI * 2;
      g += `<rect x="${cx - 22}" y="${cy - 190}" width="44" height="60" rx="6" fill="${c[0]}" transform="rotate(${(a * 180) / Math.PI} ${cx} ${cy})"/>`;
    }
    return g + `<circle cx="${cx}" cy="${cy}" r="140" fill="${c[0]}"/><circle cx="${cx}" cy="${cy}" r="60" fill="${c[1]}"/>` +
      `<rect x="${cx - 12}" y="${cy - 40}" width="24" height="80" fill="#eee"/><rect x="${cx - 40}" y="${cy - 12}" width="80" height="24" fill="#eee"/>` +
      brick(180, 590, 440, 50, c[2]);
  },
  house: (c) =>
    brick(220, 520, 360, 80, c[0]) + brick(220, 440, 360, 80, c[0]) + brick(220, 360, 360, 80, c[0]) +
    `<polygon points="200,360 400,200 600,360" fill="${c[1]}"/>` + window_(260, 400, 60, 60) + window_(480, 400, 60, 60) +
    `<rect x="365" y="480" width="70" height="120" rx="6" fill="#7a4b2a"/>` +
    `<path d="M400 300 c-20 -30 -60 -10 -40 20 l40 35 l40 -35 c20 -30 -20 -50 -40 -20z" fill="${c[2]}"/>`,
  train: (c) =>
    brick(140, 440, 360, 90, c[0]) + brick(380, 330, 120, 110, c[1]) + brick(180, 380, 60, 60, c[2]) +
    window_(400, 350, 80, 50) + brick(520, 460, 160, 70, c[1]) + wheel(200, 560, 30) + wheel(300, 560, 30) +
    wheel(430, 560, 30) + wheel(560, 560, 26) + wheel(640, 560, 26) +
    `<rect x="100" y="600" width="620" height="12" fill="#6b4f3a"/>`,
  robot: (c) =>
    brick(300, 220, 200, 120, c[0]) + `<circle cx="355" cy="280" r="22" fill="#fff"/><circle cx="445" cy="280" r="22" fill="#fff"/>` +
    `<circle cx="355" cy="280" r="10" fill="#222"/><circle cx="445" cy="280" r="10" fill="#222"/>` +
    brick(260, 350, 280, 180, c[1]) + brick(190, 360, 60, 140, c[2]) + brick(550, 360, 60, 140, c[2]) +
    brick(290, 540, 90, 90, c[2]) + brick(420, 540, 90, 90, c[2]) +
    `<rect x="340" y="400" width="120" height="60" rx="8" fill="${c[0]}"/>`,
  ship: (c) =>
    `<path d="M160 480 h480 l-60 110 h-360z" fill="${c[0]}"/>` + brick(260, 400, 280, 80, c[1]) +
    `<rect x="395" y="170" width="10" height="230" fill="#5a3b1e"/>` +
    `<polygon points="405,180 560,300 405,330" fill="#fff"/><polygon points="395,200 270,320 395,340" fill="#f2f2f2"/>` +
    `<path d="M80 620 q60 -30 120 0 t120 0 t120 0 t120 0 t120 0" stroke="#fff" stroke-width="10" fill="none" opacity=".7"/>`,
  plane: (c) =>
    `<rect x="150" y="360" width="500" height="90" rx="45" fill="${c[0]}"/>` +
    `<polygon points="330,400 470,400 360,600 300,600" fill="${c[1]}"/><polygon points="330,410 470,410 360,220 300,220" fill="${c[1]}"/>` +
    `<polygon points="160,370 220,370 170,270 140,270" fill="${c[2]}"/>` +
    window_(520, 380, 30, 30) + window_(470, 380, 30, 30) + window_(420, 380, 30, 30),
  stack: (c) =>
    brick(200, 520, 400, 100, c[0]) + brick(260, 410, 280, 100, c[1]) + brick(300, 300, 200, 100, c[2]) +
    brick(340, 200, 120, 90, c[0]),
  dragon: (c) =>
    `<path d="M200 520 q100 -220 260 -160 q120 40 160 -60 q20 80 -60 140 q-60 60 -40 140z" fill="${c[0]}"/>` +
    `<polygon points="360,370 300,230 430,330" fill="${c[1]}"/><polygon points="430,350 470,220 520,360" fill="${c[1]}"/>` +
    `<circle cx="590" cy="320" r="10" fill="#fff"/>` + brick(160, 560, 480, 60, c[2]),
};

const palettes = [
  ["#e63946", "#457b9d", "#ffb703"],
  ["#2463eb", "#ffb703", "#e63946"],
  ["#22a06b", "#ff9f1c", "#2463eb"],
  ["#ff9f1c", "#8338ec", "#22a06b"],
  ["#8338ec", "#ff006e", "#ffbe0b"],
  ["#ff006e", "#3a86ff", "#ffbe0b"],
];
const backgrounds = [
  ["#fff3c4", "#ffd166"],
  ["#d7f0ff", "#8ecae6"],
  ["#e3f9e5", "#9ee6b0"],
  ["#ffe5ec", "#ffafcc"],
  ["#ece4ff", "#c8b6ff"],
  ["#fff0e0", "#ffc49b"],
];

function svg(scene, pi, bi, label) {
  const [b1, b2] = backgrounds[bi % backgrounds.length];
  const pal = palettes[pi % palettes.length];
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="800" height="800" role="img" aria-label="${label}">
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${b1}"/><stop offset="1" stop-color="${b2}"/></linearGradient></defs>
<rect width="800" height="800" fill="url(#bg)"/>
<g opacity=".18" fill="#fff">${Array.from({ length: 8 }, (_, i) => `<circle cx="${80 + i * 95}" cy="${90 + (i % 3) * 30}" r="${14 + (i % 4) * 4}"/>`).join("")}</g>
<ellipse cx="400" cy="660" rx="300" ry="34" fill="#000" opacity=".1"/>
${scenes[scene](pal)}
</svg>
`;
}

const sceneNames = Object.keys(scenes);
let count = 0;
for (const scene of sceneNames) {
  for (let v = 0; v < 3; v++) {
    const file = path.join(OUT_PRODUCTS, `${scene}-${v + 1}.svg`);
    writeFileSync(file, svg(scene, sceneNames.indexOf(scene) + v, sceneNames.indexOf(scene) + v * 2, `Ілюстрація: ${scene}`));
    count++;
  }
}

const categoryScenes = { city: "city", technic: "technic", friends: "house", creator: "dragon", duplo: "stack", classic: "train" };
for (const [slug, scene] of Object.entries(categoryScenes)) {
  writeFileSync(path.join(OUT_CATEGORIES, `${slug}.svg`), svg(scene, sceneNames.indexOf(scene), sceneNames.indexOf(scene), slug));
  count++;
}
writeFileSync(path.join("public", "images", "hero.svg"), svg("castle", 1, 1, "Цеглинка").replace('viewBox="0 0 800 800"', 'viewBox="0 0 800 800"'));
console.log(`Згенеровано ${count + 1} SVG-файлів`);
