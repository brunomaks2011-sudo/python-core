// Seeded 2D gradient (Perlin-style) noise + fractal helpers.
import { RNG } from './Random.js';

export class Noise2D {
  constructor(seed = 1) {
    const rng = new RNG(seed);
    const p = new Uint8Array(256);
    for (let i = 0; i < 256; i++) p[i] = i;
    rng.shuffle(p);
    this.perm = new Uint8Array(512);
    for (let i = 0; i < 512; i++) this.perm[i] = p[i & 255];
    this.gx = new Float32Array(256);
    this.gy = new Float32Array(256);
    for (let i = 0; i < 256; i++) {
      const a = rng.next() * Math.PI * 2;
      this.gx[i] = Math.cos(a);
      this.gy[i] = Math.sin(a);
    }
  }

  // Returns roughly [-1, 1]
  noise(x, y) {
    const xi = Math.floor(x), yi = Math.floor(y);
    const xf = x - xi, yf = y - yi;
    const X = xi & 255, Y = yi & 255;
    const perm = this.perm;
    const g00 = perm[X + perm[Y]], g10 = perm[X + 1 + perm[Y]];
    const g01 = perm[X + perm[Y + 1]], g11 = perm[X + 1 + perm[Y + 1]];
    const d00 = this.gx[g00] * xf + this.gy[g00] * yf;
    const d10 = this.gx[g10] * (xf - 1) + this.gy[g10] * yf;
    const d01 = this.gx[g01] * xf + this.gy[g01] * (yf - 1);
    const d11 = this.gx[g11] * (xf - 1) + this.gy[g11] * (yf - 1);
    const u = xf * xf * xf * (xf * (xf * 6 - 15) + 10);
    const v = yf * yf * yf * (yf * (yf * 6 - 15) + 10);
    const a = d00 + (d10 - d00) * u;
    const b = d01 + (d11 - d01) * u;
    return (a + (b - a) * v) * 1.41421356;
  }

  fbm(x, y, octaves = 5, lacunarity = 2.0, gain = 0.5) {
    let amp = 1, freq = 1, sum = 0, norm = 0;
    for (let i = 0; i < octaves; i++) {
      sum += amp * this.noise(x * freq, y * freq);
      norm += amp;
      amp *= gain;
      freq *= lacunarity;
    }
    return sum / norm;
  }

  ridged(x, y, octaves = 5) {
    let amp = 0.5, freq = 1, sum = 0;
    for (let i = 0; i < octaves; i++) {
      const n = 1 - Math.abs(this.noise(x * freq, y * freq));
      sum += n * n * amp;
      freq *= 2;
      amp *= 0.5;
    }
    return sum;
  }
}
