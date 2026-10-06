"use client";
import { useState } from "react";
import React from "react";
export const fmtSize = (n: number) => n > 1e9 ? (n / 1e9).toFixed(2) + " GB" : n > 1e6 ? (n / 1e6).toFixed(2) + " MB" : n > 1e3 ? (n / 1e3).toFixed(1) + " KB" : n + " B";
export const fmtDate = (s?: string | null) => (s ? new Date(s).toLocaleString() : "Not Available");
const tone = (s: string) => (({ completed: "ok", ACTIVE: "ok", failed: "bad", LOCKED: "bad" }) as Record<string, string>)[s] || "warn";
export const Badge = ({ s }: { s: string }) => <span className={`badge ${tone(s)}`}>{s}</span>;
export const Card = ({ title, right, children }: { title?: string; right?: React.ReactNode; children: React.ReactNode }) => (
  <section className="card">{title && <header><h3>{title}</h3>{right}</header>}{children}</section>
);
export function Field({ label, ...r }: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return <label className="f"><span>{label}</span><input {...r} /></label>;
}
export const Stat = ({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: string; tone?: "c" | "t" | "m" }) => (
  <div className="stat"><span className="lbl">{label}</span><b className={tone}>{value}</b>{sub && <small>{sub}</small>}</div>
);
export const Brand = ({ sub }: { sub?: string }) => (
  <span className="brand"><i className="logo" aria-hidden="true" /><span>PROOFTRACE //<br />{sub || "CYBER-FORENSICS"}</span></span>
);
export const Empty = ({ text }: { text: string }) => <div className="empty">{text}</div>;
export const Skeleton = () => <div className="skel" aria-label="Loading" />;
export function Modal({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  if (!open) return null;
  return <div className="modal" role="dialog" aria-modal="true" onClick={onClose}><div onClick={(e) => e.stopPropagation()}>{children}</div></div>;
}
export function KV({ rows }: { rows: [string, React.ReactNode][] }) {
  return <table className="kv"><tbody>{rows.map(([k, v]) => <tr key={k}><th style={{ width: "34%" }}>{k}</th><td className="mono">{v as any}</td></tr>)}</tbody></table>;
}

export async function copyText(t: string): Promise<boolean> {
  try { await navigator.clipboard.writeText(t); return true; } catch {}
  try {
    const a = document.createElement("textarea"); a.value = t; a.style.position = "fixed"; a.style.opacity = "0";
    document.body.appendChild(a); a.select(); const ok = document.execCommand("copy"); a.remove(); return ok;
  } catch { return false; }
}
export function CopyBtn({ text, label, caption }: { text: string; label?: string; caption?: string }) {
  const [ok, setOk] = useState(false);
  return <button type="button" className="cp" title="Copy to clipboard" aria-label={`Copy ${label || "value"}`}
    onClick={async () => { if (await copyText(text)) { setOk(true); setTimeout(() => setOk(false), 1300); } }}>{ok ? "Copied" : caption || "Copy"}</button>;
}
export function PasswordField({ label, ...r }: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  const [show, setShow] = useState(false);
  return (
    <label className="f"><span>{label}</span>
      <div className="pw"><input {...r} type={show ? "text" : "password"} />
        <button type="button" className="eye" aria-label={show ? "Hide password" : "Show password"} onClick={() => setShow(!show)}>{show ? "Hide" : "Show"}</button></div>
    </label>
  );
}
