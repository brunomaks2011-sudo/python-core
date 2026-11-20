// Hand-authored strategic layout of the "Dolyna Valley" battlefield: a fictional
// Eastern European river valley. Coordinates in metres, X = east, Z = south.
// The procedural generator (gen_map.mjs) turns this into terrain, roads,
// buildings, props and vegetation.

export const MAP_ID = 'dolyna_valley';
export const MAP_NAME = 'Dolyna Valley';
export const HALF = 1024; // terrain spans [-1024, 1024]
export const CELL = 2; // heightmap resolution (m)
export const N = HALF * 2 / CELL + 1; // 1025 samples per side
export const PLAYABLE = { minX: -720, maxX: 720, minZ: -720, maxZ: 720 };

export const BASE_HEIGHT = 20;
export const WATER_LEVEL = 15.0;
export const RIVER_WIDTH = 26;

export function riverX(z) {
  return 245 + 38 * Math.sin(z * 0.0042 + 0.5) + 14 * Math.sin(z * 0.012 + 1.3);
}

export const POINTS = [
  { id: 'A', name: 'Industrial Complex', x: -430, z: -62, radius: 38, zone: 'industrial' },
  { id: 'B', name: 'Dolyna Village', x: 0, z: 40, radius: 34, zone: 'village' },
  { id: 'C', name: 'Military Base', x: 455, z: 0, radius: 38, zone: 'base' },
];

export const HQS = [
  { team: 1, name: 'Blue Army FOB "Anvil"', x: -60, z: 632, radius: 70, faceYaw: 0 },
  { team: 2, name: 'Red Army FOB "Hammer"', x: 70, z: -628, radius: 70, faceYaw: Math.PI },
];

// Roads: kind = highway | road | street | dirt. Control points are smoothed.
export const ROADS = [
  {
    id: 'highway', kind: 'highway', width: 11,
    ctrl: [[-1100, 105], [-760, 98], [-560, 88], [-430, 82], [-300, 92], [-150, 102], [0, 110], [130, 108],
      [230, 100], [300, 104], [370, 128], [450, 172], [560, 180], [760, 172], [1100, 160]],
  },
  {
    id: 'main_street', kind: 'road', width: 8,
    ctrl: [[70, -628], [62, -470], [42, -310], [22, -190], [10, -125], [4, -40], [0, 40], [0, 110], [-12, 250], [-40, 430], [-60, 632]],
  },
  {
    id: 'road_blue_A', kind: 'road', width: 7,
    ctrl: [[-60, 632], [-190, 540], [-320, 420], [-415, 270], [-438, 140], [-440, 84], [-440, 44], [-432, -20]],
  },
  {
    id: 'road_red_A', kind: 'road', width: 7,
    ctrl: [[70, -628], [-110, -540], [-290, -430], [-400, -310], [-428, -215], [-430, -120]],
  },
  {
    id: 'road_blue_C', kind: 'road', width: 7,
    ctrl: [[-60, 632], [90, 575], [215, 485], [300, 405], [400, 320], [452, 240], [455, 176], [455, 132], [455, 40]],
  },
  {
    id: 'road_red_C', kind: 'dirt', width: 6, ford: true,
    ctrl: [[70, -628], [170, -540], [214, -440], [300, -370], [440, -280], [520, -200], [520, -134], [505, -100]],
  },
  {
    id: 'street_ew', kind: 'street', width: 7,
    ctrl: [[-175, 42], [-90, 36], [0, 40], [90, 44], [175, 30]],
  },
  {
    id: 'street_north', kind: 'street', width: 6,
    ctrl: [[-130, -28], [-60, -44], [4, -46], [70, -40], [120, -30]],
  },
  {
    id: 'lane_sw', kind: 'street', width: 5,
    ctrl: [[-90, 36], [-104, 70], [-112, 104]],
  },
  {
    id: 'lane_e', kind: 'street', width: 5,
    ctrl: [[90, 44], [124, 72], [150, 106]],
  },
  {
    id: 'track_A_B', kind: 'dirt', width: 5,
    ctrl: [[-300, -90], [-230, -76], [-170, -55], [-130, -28]],
  },
  {
    id: 'track_south_fields', kind: 'dirt', width: 4.5,
    ctrl: [[-330, 300], [-200, 300], [-70, 315], [60, 300], [190, 320]],
  },
  {
    id: 'track_north_fields', kind: 'dirt', width: 4.5,
    ctrl: [[-270, -330], [-150, -300], [-20, -300], [100, -290], [200, -300]],
  },
  {
    id: 'base_ring', kind: 'street', width: 6,
    ctrl: [[455, 40], [410, 52], [390, 90], [455, 112], [520, 90], [505, 52], [455, 40]],
  },
  {
    id: 'base_north', kind: 'street', width: 6,
    ctrl: [[505, -100], [500, -48], [455, -40]],
  },
];

export const RAIL = {
  ctrl: [[-1100, -178], [-760, -172], [-560, -186], [-430, -192], [-300, -172], [-150, -142], [0, -126], [150, -132],
    [240, -142], [330, -152], [420, -158], [560, -162], [760, -168], [1100, -172]],
  gauge: 1.52,
};

// Areas
export const ZONES = [
  { id: 'industrial', name: 'Kirov Works (Industrial Complex)', rect: [-565, -208, -295, 48], flattenTo: null },
  { id: 'base', name: 'Garrison 41 (Military Base)', rect: [348, -138, 572, 138], flattenTo: null },
  { id: 'village', name: 'Dolyna Village', circle: [0, 30, 185] },
  { id: 'hq_blue', name: 'FOB Anvil', circle: [-60, 632, 75] },
  { id: 'hq_red', name: 'FOB Hammer', circle: [70, -628, 75] },
];

export const HILLS = [
  { x: -720, z: -620, h: 40, r: 300 },
  { x: -720, z: 610, h: 30, r: 270 },
  { x: 720, z: -660, h: 34, r: 270 },
  { x: 720, z: 660, h: 42, r: 290 },
  { x: -660, z: -60, h: 20, r: 170 }, // ridge west of the industrial complex
  { x: -170, z: -270, h: 9, r: 150 },
  { x: 660, z: 40, h: 17, r: 150 }, // hill east of the base
  { x: -250, z: 470, h: 8, r: 170 },
  { x: 150, z: -420, h: 7, r: 140 },
];

export const FIELDS = [
  { poly: [[-385, 182], [-130, 172], [-122, 290], [-380, 290]], crops: ['wheat', 'plowed', 'green'] },
  { poly: [[-380, 312], [-122, 310], [-112, 430], [-345, 470]], crops: ['sunflower', 'wheat'] },
  { poly: [[52, 182], [228, 192], [226, 300], [48, 290]], crops: ['plowed', 'wheat'] },
  { poly: [[46, 326], [214, 334], [196, 430], [40, 440]], crops: ['green', 'sunflower', 'plowed'] },
  { poly: [[-335, -262], [-70, -246], [-62, -290], [-325, -312]], crops: ['wheat'] },
  { poly: [[-322, -342], [-60, -318], [-52, -428], [-282, -470]], crops: ['plowed', 'green', 'wheat'] },
  { poly: [[86, -238], [196, -246], [196, -282], [90, -278]], crops: ['wheat'] },
  { poly: [[92, -312], [196, -318], [186, -400], [96, -414]], crops: ['sunflower', 'plowed'] },
  { poly: [[318, 252], [640, 236], [650, 420], [332, 448]], crops: ['wheat', 'green', 'plowed', 'wheat'] },
  { poly: [[336, -256], [640, -262], [636, -432], [336, -420]], crops: ['plowed', 'wheat', 'sunflower'] },
];

// Forest blobs (centre, radius, type mix). Outer ring is forested separately.
export const FORESTS = [
  { x: -640, z: -520, r: 240, mix: 'conifer' },
  { x: -630, z: 470, r: 210, mix: 'mixed' },
  { x: 610, z: -560, r: 230, mix: 'conifer' },
  { x: 630, z: 530, r: 210, mix: 'mixed' },
  { x: -235, z: -175, r: 95, mix: 'deciduous' },
  { x: -255, z: -5, r: 62, mix: 'deciduous' },
  { x: 655, z: -20, r: 120, mix: 'mixed' },
  { x: 160, z: -200, r: 55, mix: 'birch' },
  { x: -230, z: 560, r: 90, mix: 'birch' },
  { x: 250, z: 560, r: 80, mix: 'mixed' },
  { x: -560, z: 240, r: 85, mix: 'deciduous' },
  { x: 560, z: -300, r: 70, mix: 'birch' },
];

// Area that starts the match already shelled (abandoned / destroyed urban area).
export const RUINED_AREA = { x: 140, z: 0, r: 75 };
