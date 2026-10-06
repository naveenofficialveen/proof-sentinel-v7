"use client";
import { useEffect, useRef } from "react";

/** Decorative 3D background: two counter-rotating wireframe icosahedra and drifting particles (plain canvas, no libraries). */
export default function Bg3D() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current; const ctx = cv?.getContext("2d");
    if (!cv || !ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const t = (1 + Math.sqrt(5)) / 2;
    const V = [[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t], [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]];
    const E: [number, number][] = [];
    for (let i = 0; i < 12; i++) for (let j = i + 1; j < 12; j++) {
      const d = Math.hypot(V[i][0] - V[j][0], V[i][1] - V[j][1], V[i][2] - V[j][2]);
      if (Math.abs(d - 2) < 0.01) E.push([i, j]);
    }
    const N = window.innerWidth < 700 ? 40 : 90;
    const P = Array.from({ length: N }, () => {
      const u = Math.random() * 2 - 1, a = Math.random() * Math.PI * 2, r = 1.6 + Math.random() * 0.9, s = Math.sqrt(1 - u * u);
      return [r * s * Math.cos(a), r * u, r * s * Math.sin(a)];
    });
    let w = 0, h = 0;
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = window.innerWidth; h = window.innerHeight; cv.width = w * dpr; cv.height = h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    const rot = (p: number[], ax: number, ay: number) => {
      let [x, y, z] = p;
      const cy = Math.cos(ay), sy = Math.sin(ay); [x, z] = [x * cy + z * sy, -x * sy + z * cy];
      const cx = Math.cos(ax), sx = Math.sin(ax); [y, z] = [y * cx - z * sx, y * sx + z * cx];
      return [x, y, z];
    };
    const draw = (time: number) => {
      ctx.clearRect(0, 0, w, h);
      const cx0 = w * (w < 800 ? 0.5 : 0.8), cy0 = h * 0.45, R = Math.min(w, h) * 0.2, f = 6;
      const proj = (p: number[]) => { const k = f / (f + p[2]); return [cx0 + p[0] * R * k, cy0 + p[1] * R * k, k]; };
      const ay = time * 0.00025, ax = time * 0.00015;
      for (const [scale, dir, alpha] of [[1, 1, 0.35], [0.55, -1, 0.5]] as [number, number, number][]) {
        const pts = V.map((v) => proj(rot(v.map((c) => c * scale), ax * dir, ay * dir)));
        ctx.strokeStyle = `rgba(0,229,255,${alpha})`; ctx.lineWidth = 1; ctx.beginPath();
        for (const [i, j] of E) { ctx.moveTo(pts[i][0], pts[i][1]); ctx.lineTo(pts[j][0], pts[j][1]); }
        ctx.stroke();
        ctx.fillStyle = `rgba(195,245,255,${alpha + 0.2})`;
        for (const p of pts) { ctx.beginPath(); ctx.arc(p[0], p[1], 2.2 * p[2], 0, 7); ctx.fill(); }
      }
      for (const p of P) {
        const q = proj(rot(p, ax * 0.6, ay * 0.6)); const a = Math.max(0.08, Math.min(0.7, q[2] - 0.4));
        ctx.fillStyle = `rgba(49,254,212,${a})`; ctx.beginPath(); ctx.arc(q[0], q[1], 1.4 * q[2], 0, 7); ctx.fill();
      }
    };
    let raf = 0;
    const loop = (time: number) => { draw(time); raf = requestAnimationFrame(loop); };
    resize(); window.addEventListener("resize", resize);
    if (reduce) draw(0); else raf = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); };
  }, []);
  return <canvas ref={ref} className="bg3d" aria-hidden="true" />;
}
