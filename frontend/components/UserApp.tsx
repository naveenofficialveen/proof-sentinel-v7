"use client";
import { useCallback, useEffect, useState } from "react";
import { api, post, uploadFile, API } from "../lib/api";
import { Badge, Card, CopyBtn, Empty, Field, KV, Modal, PasswordField, Skeleton, Stat, fmtDate, fmtSize } from "./ui";
import { LEGAL, LegalDoc } from "./legal";
import Forensics from "./Forensics";

type View = "dashboard" | "upload" | "metadata" | "editor" | "remover" | "results" | "reports" | "profile";
const NAV: [View, string][] = [["dashboard", "Dashboard"], ["upload", "Upload Evidence"], ["metadata", "Metadata Viewer"], ["editor", "Metadata Editor"], ["remover", "Metadata Remover"], ["results", "Analysis Results"], ["reports", "Reports"], ["profile", "Profile"]];
const PENDING = ["uploaded", "queued", "analyzing"];

type Mode = "home" | "signin" | "signup" | "forgot";

export default function UserApp() {
  const [user, setUser] = useState<any>(null);
  const [boot, setBoot] = useState(true);
  const [locked, setLocked] = useState(false);
  const [mode, setMode] = useState<Mode>("home");
  const [notice, setNotice] = useState("");
  const [legal, setLegal] = useState<LegalDoc | null>(null);
  const [askLogout, setAskLogout] = useState(false);
  const [view, setView] = useState<View>("dashboard");
  const [sel, setSel] = useState<number | null>(null);

  const loadMe = useCallback(() => api("/api/auth/me").then(setUser).catch(() => setUser(null)).finally(() => setBoot(false)), []);
  useEffect(() => {
    loadMe();
    const h = () => setLocked(true);
    window.addEventListener("account-locked", h);
    return () => window.removeEventListener("account-locked", h);
  }, [loadMe]);

  async function logout() { await post("/api/auth/logout").catch(() => {}); setAskLogout(false); setUser(null); setLocked(false); setMode("home"); }
  const open = (id: number, v: View) => { setSel(id); setView(v); };

  if (boot) return <div className="center"><Skeleton /></div>;
  if (locked) return (
    <div className="center"><Card title="Account locked">
      <p>Your account has been locked by an administrator. You cannot upload or view evidence until it is unlocked. Contact your administrator for help.</p>
      <button className="btn ghost" onClick={logout}>Back to home</button>
    </Card></div>
  );

  if (!user) return (
    <>
      <header className="top">
        {mode === "home" && <span className="node"><i />SYSTEM ONLINE</span>}
        <span className="sp" />
        <button className={`nl ${mode === "home" ? "on" : ""}`} onClick={() => { setNotice(""); setMode("home"); }}>Home</button>
        <button className="btn ghost sm" onClick={() => { setNotice(""); setMode("signin"); }}>Sign In</button>
        <button className="btn sm" onClick={() => { setNotice(""); setMode("signup"); }}>Sign Up</button>
      </header>
      {mode === "home" ? <Landing go={setMode} />
        : mode === "forgot" ? <Forgot setMode={setMode} onDone={() => { setNotice("Password updated. Please sign in with your new password."); setMode("signin"); }} />
        : <Auth mode={mode} setMode={setMode} onDone={loadMe} notice={notice} />}
      <footer className="foot">
        <button className="nl" onClick={() => setLegal("terms")}>Terms &amp; Conditions</button>
        <button className="nl" onClick={() => setLegal("privacy")}>Privacy Policy</button>
        <span>Digital Proof Verification and Evidence Analysis System</span>
      </footer>
      <Modal open={!!legal} onClose={() => setLegal(null)}>
        {legal && <>
          <h2>{LEGAL[legal].title}</h2>
          {LEGAL[legal].sections.map(([h, t]) => <div key={h} style={{ marginTop: 14 }}><h3>{h}</h3><p className="note" style={{ color: "var(--mute)" }}>{t}</p></div>)}
          <div className="acts"><button className="btn ghost" onClick={() => setLegal(null)}>Close</button></div>
        </>}
      </Modal>
    </>
  );

  return (
    <>
      <header className="top"><span className="node"><i />SESSION ACTIVE</span><span className="sp" /><span className="who">{user.email}</span></header>
      <div className="shell">
        <aside className="side">
          {NAV.map(([v, l]) => <button key={v} className={view === v ? "on" : ""} onClick={() => setView(v)}>{l}</button>)}
          <button onClick={() => setAskLogout(true)}>Logout</button>
        </aside>
        <main className="main">
          {view === "dashboard" && <Dashboard open={open} go={setView} />}
          {view === "upload" && <Upload open={open} />}
          {(view === "metadata" || view === "results") && <Evidence mode={view} sel={sel} setSel={setSel} />}
          {view === "editor" && <Editor sel={sel} setSel={setSel} />}
          {view === "remover" && <Remover sel={sel} setSel={setSel} />}
          {view === "reports" && <Reports />}
          {view === "profile" && <Card title="Profile"><KV rows={[["Name", user.name], ["Email", user.email], ["Registered", fmtDate(user.created_at)]]} /></Card>}
        </main>
      </div>
      <Modal open={askLogout} onClose={() => setAskLogout(false)}>
        <h3>Confirm logout</h3>
        <p>Are you sure you want to log out?</p>
        <div className="acts">
          <button className="btn ghost" onClick={() => setAskLogout(false)}>Stay signed in</button>
          <button className="btn danger" onClick={logout}>Yes, log out</button>
        </div>
      </Modal>
    </>
  );
}

function Landing({ go }: { go: (m: Mode) => void }) {
  const caps: [string, string, string, ("c" | "t" | "m" | undefined)][] = [
    ["Hashing", "SHA-256", "Integrity check on every upload", "c"],
    ["Files & docs", "PDF, DOCX, ZIP", "Metadata and structure analysis", undefined],
    ["Images", "EXIF + OCR", "Camera data and readable text", "t"],
    ["Video", "Streams + frames", "Codecs, duration, frame OCR", undefined],
    ["Processing", "Async queue", "Celery and Redis workers", "m"],
    ["Reports", "PDF export", "Technical report per analysis", "c"],
  ];
  return (
    <main>
      <section className="hero">
        <div className="badges"><span className="chip"><i />SHA-256 integrity</span><span className="chip">Metadata extraction</span><span className="chip">OCR analysis</span></div>
        <h1>Digital Proof Verification and Evidence Analysis System</h1>
        <p>A secure platform for analyzing digital evidence, extracting technical metadata, verifying file integrity, and generating structured evidence reports.</p>
        <div className="row"><button className="btn" onClick={() => go("signup")}>Get Started</button><button className="btn ghost" onClick={() => go("signin")}>Sign In</button></div>
      </section>
      <section className="wrap">
        <div className="sec-h"><span>Platform capabilities</span></div>
        <div className="grid">{caps.map(([l, v, sub, t]) => <Stat key={l} label={l} value={v} sub={sub} tone={t} />)}</div>
      </section>
    </main>
  );
}

function Auth({ mode, setMode, onDone, notice }: { mode: string; setMode: (m: Mode) => void; onDone: () => void; notice: string }) {
  const [f, setF] = useState({ name: "", email: "", password: "" });
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const up = mode === "signup";
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      if (up) await post("/api/auth/signup", f);
      await post("/api/auth/signin", { email: f.email, password: f.password });
      onDone();
    } catch (x: any) { setErr(x.message === "ACCOUNT_LOCKED" ? "This account is locked. Contact your administrator." : x.message); }
    setBusy(false);
  }
  return (
    <div className="center"><Card title={up ? "Create your account" : "Sign in"}>
      {notice && !up && <div className="ok-msg" role="status">{notice}</div>}
      <form onSubmit={submit}>
        {up && <Field label="Full name" required minLength={2} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />}
        <Field label="Email" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        <PasswordField label={up ? "Password (at least 10 characters)" : "Password"} type="password" required minLength={up ? 10 : 1} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        {err && <div className="err" role="alert">{err}</div>}
        <button className="btn" disabled={busy}>{busy ? "Please wait" : up ? "Create account" : "Sign in"}</button>
      </form>
      {!up && <p className="note"><a href="#" onClick={(e) => { e.preventDefault(); setMode("forgot"); }}>Forgot password?</a></p>}
      <p className="note">{up ? "Already registered? " : "New here? "}<a href="#" onClick={(e) => { e.preventDefault(); setMode(up ? "signin" : "signup"); }}>{up ? "Sign in" : "Create an account"}</a></p>
    </Card></div>
  );
}

function Forgot({ setMode, onDone }: { setMode: (m: Mode) => void; onDone: () => void }) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [email, setEmail] = useState(""); const [otp, setOtp] = useState(""); const [p1, setP1] = useState(""); const [p2, setP2] = useState("");
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false); const [wait, setWait] = useState(0);
  const [mailOk, setMailOk] = useState<boolean | null>(null); const [demo, setDemo] = useState(false);
  useEffect(() => { api("/api/auth/mail-status").then((r) => { setMailOk(r.configured); setDemo(!!r.demo); }).catch(() => {}); }, []);
  useEffect(() => { if (wait <= 0) return; const t = setTimeout(() => setWait(wait - 1), 1000); return () => clearTimeout(t); }, [wait]);
  useEffect(() => { window.scrollTo(0, 0); setErr(""); }, [step]);

  async function sendCode(e?: React.FormEvent) {
    e?.preventDefault(); setErr(""); setBusy(true);
    try {
      const r = await post("/api/auth/forgot", { email });
      if (r.demo_code) { setOtp(r.demo_code); setStep(3); } else { setStep(2); setWait(60); }
    } catch (x: any) { setErr(x.message); }
    setBusy(false);
  }
  async function checkCode(e: React.FormEvent) {
    e.preventDefault(); setErr(""); setBusy(true);
    try { await post("/api/auth/verify-otp", { email, otp }); setStep(3); } catch (x: any) { setErr(x.message); }
    setBusy(false);
  }
  async function setPassword(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    if (p1 !== p2) { setErr("The two passwords do not match."); return; }
    setBusy(true);
    try { await post("/api/auth/reset", { email, otp, password: p1 }); onDone(); } catch (x: any) { setErr(x.message); }
    setBusy(false);
  }
  const toSignIn = <p className="note"><a href="#" onClick={(e) => { e.preventDefault(); setMode("signin"); }}>Back to sign in</a></p>;

  if (step === 3) return (
    <div className="center"><Card title="Set a new password">
      <form onSubmit={setPassword}>
        <PasswordField label="New password (at least 10 characters)" required minLength={10} autoComplete="new-password" value={p1} onChange={(e) => setP1(e.target.value)} />
        <PasswordField label="Confirm new password" required minLength={10} autoComplete="new-password" value={p2} onChange={(e) => setP2(e.target.value)} />
        {err && <div className="err" role="alert">{err}</div>}
        <button className="btn" disabled={busy}>{busy ? "Please wait" : "Reset password"}</button>
      </form>
      {err.includes("code") && <p className="note"><a href="#" onClick={(e) => { e.preventDefault(); setOtp(""); setStep(1); }}>Start again</a></p>}
    </Card></div>
  );
  if (step === 2) return (
    <div className="center"><Card title="Enter the code">
      <p className="note">We sent a 6-digit code to <b>{email}</b>. It is valid for 10 minutes.</p>
      {mailOk === false && <p className="note">No mail account is set up on this server, so the code is in the backend log (Docker Desktop, backend container, Logs).</p>}
      <form onSubmit={checkCode}>
        <Field label="6-digit code" required inputMode="numeric" maxLength={6} pattern="\d{6}" autoComplete="one-time-code" value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))} />
        {err && <div className="err" role="alert">{err}</div>}
        <button className="btn" disabled={busy || otp.length !== 6}>{busy ? "Please wait" : "Verify code"}</button>{" "}
        <button type="button" className="btn ghost sm" disabled={busy || wait > 0} onClick={() => sendCode()}>{wait > 0 ? `Resend code (${wait}s)` : "Resend code"}</button>
      </form>
      <p className="note"><a href="#" onClick={(e) => { e.preventDefault(); setStep(1); }}>Use a different email</a></p>
    </Card></div>
  );
  return (
    <div className="center"><Card title="Forgot password">
      {demo && <div className="warn-box" role="note">Local test mode: no e-mail account is set up, so no code is needed. After you enter the email you only choose a new password.</div>}
      {mailOk === false && !demo && <div className="warn-box" role="note">E-mail sending is not set up on this server yet, so no code will arrive in an inbox. The site owner must add the mail account in the .env file.</div>}
      <form onSubmit={sendCode}>
        <p className="note">Enter your account email. We will send a 6-digit code to it.</p>
        <Field label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        {err && <div className="err" role="alert">{err}</div>}
        <button className="btn" disabled={busy}>{busy ? "Please wait" : demo ? "Continue" : "Send code"}</button>
      </form>
      {toSignIn}
    </Card></div>
  );
}

function usePolledList() {
  const [list, setList] = useState<any[] | null>(null); const [err, setErr] = useState("");
  const load = useCallback(() => api("/api/evidence").then((l) => { setList(l); setErr(""); }).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (!list?.some((e) => PENDING.includes(e.status))) return; const t = setTimeout(load, 3000); return () => clearTimeout(t); }, [list, load]);
  return { list, err, load };
}

function EvTable({ list, onPick, label }: { list: any[]; onPick: (id: number) => void; label: string }) {
  if (!list.length) return <Empty text="No evidence yet. Upload a file to start an analysis." />;
  return <table><thead><tr><th>File</th><th>Type</th><th>Size</th><th>Status</th><th>Uploaded</th><th /></tr></thead><tbody>
    {list.map((e) => <tr key={e.id}><td>{e.name}{e.derived_op && <div className="note">{e.derived_op === "metadata_removed" ? "Clean copy (metadata removed)" : "Edited copy (metadata changed)"}</div>}</td><td>{e.category || e.mime || "Pending"}</td><td>{fmtSize(e.size)}</td>
      <td><Badge s={e.status} />{e.error && <div className="err">{e.error}</div>}</td><td>{fmtDate(e.created_at)}</td>
      <td><button className="btn ghost" onClick={() => onPick(e.id)}>{label}</button></td></tr>)}
  </tbody></table>;
}

function Dashboard({ open, go }: { open: (id: number, v: View) => void; go: (v: View) => void }) {
  const [s, setS] = useState<any>(null); const { list, err } = usePolledList();
  useEffect(() => { api("/api/dashboard").then(setS).catch(() => {}); }, [list]);
  return <>
    <h2>Dashboard</h2>
    <div className="grid tools">
      {([["metadata", "Metadata Viewer", "Camera, device, dates and every field stored in a file"], ["editor", "Metadata Editor", "Change selected fields and save a new copy"], ["remover", "Metadata Remover", "Strip location, camera and author data into a clean copy"]] as [View, string, string][]).map(([v, t, d]) =>
        <button key={v} className="tool" onClick={() => go(v)}><b>{t}</b><span>{d}</span></button>)}
    </div>
    {!s ? <Skeleton /> : <div className="grid">
      <Stat label="Total uploaded evidence" value={s.total} tone="c" /><Stat label="Files" value={s.files} /><Stat label="Images" value={s.images} tone="t" />
      <Stat label="Videos" value={s.videos} /><Stat label="Completed analysis" value={s.completed} tone="m" /><Stat label="Generated reports" value={s.reports} tone="c" /></div>}
    <Card title="Recent evidence">{err ? <div className="err">{err}</div> : !list ? <Skeleton /> : <EvTable list={list.slice(0, 8)} onPick={(id) => open(id, "results")} label="Open" />}</Card>
  </>;
}

function Upload({ open }: { open: (id: number, v: View) => void }) {
  const { list, load } = usePolledList();
  const [prog, setProg] = useState<Record<string, { p: number; err?: string }>>({}); const [over, setOver] = useState(false);
  async function go(files: FileList | File[]) {
    for (const f of Array.from(files)) {
      const k = f.name + f.size;
      if (f.size > 100 * 1024 * 1024) { setProg((s) => ({ ...s, [k]: { p: 0, err: `${f.name}: file is larger than the 100 MB limit` } })); continue; } setProg((s) => ({ ...s, [k]: { p: 0 } }));
      try { await uploadFile(f, (p) => setProg((s) => ({ ...s, [k]: { p } }))); setProg((s) => ({ ...s, [k]: { p: 100 } })); load(); }
      catch (e: any) { setProg((s) => ({ ...s, [k]: { p: 0, err: `${f.name}: ${e.message}` } })); }
    }
  }
  return <>
    <h2>Upload Evidence</h2>
    <label className={`drop ${over ? "over" : ""}`} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); go(e.dataTransfer.files); }}>
      <span className="dz-icon" aria-hidden="true"><svg width="26" height="20" viewBox="0 0 26 20" fill="none" stroke="#00e5ff" strokeWidth="2"><path d="M13 18V7M8 11l5-5 5 5M4 18h18" /></svg></span>
      <strong>Drag and Drop Forensic Evidence Artifact</strong>
      <span>Images, videos, audio, documents, archives and more. Maximum 100 MB per file.</span>
      <span className="btn sm">Browse Local Drives</span>
      <input type="file" multiple hidden onChange={(e) => e.target.files && go(e.target.files)} />
    </label>
    {(Object.entries(prog) as [string, { p: number; err?: string }][]).map(([k, v]) => <div key={k}>{v.err ? <div className="err">{v.err}</div> : <div className="bar" role="progressbar" aria-valuenow={v.p}><i style={{ width: v.p + "%" }} /></div>}</div>)}
    <Card title="Your uploads">{!list ? <Skeleton /> : <EvTable list={list} onPick={(id) => open(id, "results")} label="View results" />}</Card>
  </>;
}

const GROUPS: [string, RegExp][] = [
  ["Date information", /date|time|created|modified|saved/i], ["Device information", /make|model|device|camera|lens/i],
  ["Software information", /software|encoder|application|producer|creator/i],
  ["Media information", /duration|resolution|dimension|frame|codec|bit rate|sample|channels|format|container|streams|pages|mode/i]];

function Evidence({ mode, sel, setSel }: { mode: "metadata" | "results"; sel: number | null; setSel: (n: number) => void }) {
  const { list, err } = usePolledList();
  return <>
    <h2>{mode === "metadata" ? "Metadata" : "Analysis Results"}</h2>
    {err && <div className="err">{err}</div>}
    {!list ? <Skeleton /> : <Card title="Choose evidence"><EvTable list={list} onPick={setSel} label="Select" /></Card>}
    {sel && <Detail id={sel} mode={mode} />}
  </>;
}

function Detail({ id, mode }: { id: number; mode: "metadata" | "results" }) {
  const [d, setD] = useState<any>(null); const [tab, setTab] = useState("ocr"); const [err, setErr] = useState("");
  useEffect(() => {
    let t: any; let dead = false;
    const load = () => api(`/api/evidence/${id}`).then((x) => { if (dead) return; setD(x); if (PENDING.includes(x.status)) t = setTimeout(load, 3000); }).catch((e) => setErr(e.message));
    setD(null); load(); return () => { dead = true; clearTimeout(t); };
  }, [id]);
  if (err) return <div className="err">{err}</div>;
  if (!d) return <Skeleton />;
  if (PENDING.includes(d.status)) return <Card title={d.name}><Badge s={d.status === "analyzing" ? "Analyzing..." : "Processing..."} /><p className="note">This page updates automatically.</p></Card>;
  if (d.status === "failed") return <Card title={d.name}><Badge s="failed" /><p className="err">{d.error || "Analysis failed"}</p></Card>;

  const m = d.metadata; const spec: Record<string, any> = m?.specific || {};
  const groups: Record<string, [string, any][]> = {}; const other: [string, any][] = [];
  Object.entries(spec).forEach(([k, v]) => { const g = GROUPS.find(([, re]) => re.test(k)); if (g) (groups[g[0]] ||= []).push([k, v]); else other.push([k, v]); });
  const report = d.report_id && <>
    <a className="btn ghost" href={`${API}/api/reports/${d.report_id}/view`} target="_blank" rel="noreferrer">View Report</a>{" "}
    <a className="btn" href={`${API}/api/reports/${d.report_id}/download`} download>Download Report</a></>;

  return <Card title={d.name} right={<div>{report}</div>}>
    {mode === "metadata" ? (!m ? <Empty text="Unsupported / Analysis Not Available" /> : <><CameraCard cam={m.camera} isImage={d.category === "image"} /><MetaViewer d={d} /><Forensics d={d} /></>) : <>
      <div className="tabs">{[["ocr", "OCR"], ["structure", "File structure"], ["signature", "Digital signature"], ["integrity", "SHA-256 / Integrity"]].map(([k, l]) =>
        <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}</div>
      {tab === "ocr" && (!d.ocr || d.ocr.status === "not_applicable" ? <Empty text="OCR does not apply to this file type." /> :
        d.ocr.status === "completed" ? <><p className="note">OCR completed. Mean confidence: {d.ocr.confidence ?? "Not Available"}</p><pre>{d.ocr.text}</pre>
          {d.ocr.frames?.filter((f: any) => f.text).map((f: any) => <p key={f.frame}><b>Frame {f.frame}:</b> {f.text}</p>)}</> :
          <Empty text={d.ocr.status === "no_text_detected" ? "OCR finished. No readable text was detected." : "OCR failed for this file."} />)}
      {tab === "structure" && (d.analysis?.structure?.length ? <table><tbody>{d.analysis.structure.map((s: any, i: number) => <tr key={i}><td className="mono">{JSON.stringify(s)}</td></tr>)}</tbody></table> :
        <Empty text={m ? "No structural components reported for this format." : "Unsupported / Analysis Not Available"} />)}
      {tab === "signature" && <KV rows={[["Status", d.analysis?.signature?.status || "Not Available"], ["Detail", d.analysis?.signature?.detail || "None"]]} />}
      {tab === "integrity" && <KV rows={[["SHA-256", d.sha256], ["Hash generation", "Completed"], ["Integrity check", d.integrity || "Not Available"], ["Analyzed", fmtDate(d.analysis?.completed_at)], ...((d.derived_op ? [["Origin", d.derived_op === "metadata_removed" ? "Clean copy made by the Metadata Remover" : "Edited copy made by the Metadata Editor"], ["Derived from evidence ID", d.derived_from], ["Changes", d.derived_note || "Not Available"]] : []) as [string, any][])]} />}
    </>}
  </Card>;
}

function Reports() {
  const [rows, setRows] = useState<any[] | null>(null);
  useEffect(() => { api("/api/reports").then(setRows).catch(() => setRows([])); }, []);
  return <>
    <h2>Reports</h2>
    {!rows ? <Skeleton /> : !rows.length ? <Empty text="No reports yet. A report is created when an analysis completes." /> :
      <Card><table><thead><tr><th>Evidence</th><th>Generated</th><th /></tr></thead><tbody>{rows.map((r) =>
        <tr key={r.id}><td>{r.file}</td><td>{fmtDate(r.created_at)}</td><td>
          <a className="btn ghost" href={`${API}/api/reports/${r.id}/view`} target="_blank" rel="noreferrer">View Report</a>{" "}
          <a className="btn" href={`${API}/api/reports/${r.id}/download`} download>Download Report</a></td></tr>)}</tbody></table></Card>}
  </>;
}

function PropRow({ k, v }: { k: string; v: string }) {
  return <div className="prop"><span className="pk">{k}</span><span className="pv mono">{v}</span><CopyBtn text={v} label={k} /></div>;
}

function CameraCard({ cam, isImage }: { cam?: Record<string, string>; isImage?: boolean }) {
  const has = !!cam && Object.keys(cam).length > 0;
  return (
    <div style={{ marginBottom: 18 }}>
      <h3 className="cam-h">Camera info</h3>
      {!has ? <Empty text={isImage ? "No camera or device information is stored in this file. Apps such as WhatsApp, Instagram and Telegram, and screenshots, remove it. Upload the original photo from the phone's camera folder, or send it as a Document." : "No camera or device information is stored in this file."} /> : <>
        {cam!.Device && <p className="cam-big">This file was captured with <b>{cam!.Device}</b> <CopyBtn text={cam!.Device} label="device name" /></p>}
        <div className="prop-grid">{Object.entries(cam!).filter(([k]) => k !== "Device").map(([k, v]) => <PropRow key={k} k={k} v={String(v)} />)}</div>
        <p className="note">Reported by the file's own metadata, which can be edited. It does not prove which device captured the file.</p></>}
    </div>
  );
}

function MetaViewer({ d }: { d: any }) {
  const m = d.metadata; const spec: Record<string, any> = m?.specific || {};
  const sections: [string, [string, string][]][] = [];
  const add = (name: string, rows: [string, any][]) => { if (rows.length) sections.push([name, rows.map(([k, v]) => [k, String(v)] as [string, string])]); };
  const groups: Record<string, [string, any][]> = {}; const other: [string, any][] = [];
  Object.entries(spec).forEach(([k, v]) => { const g = GROUPS.find(([, re]) => re.test(k)); if (g) (groups[g[0]] ||= []).push([k, v]); else other.push([k, v]); });
  add("General", Object.entries(m.general));
  GROUPS.forEach(([name]) => add(name, groups[name] || []));
  add("Other properties", other);
  add("Security", [["SHA-256", d.sha256], ["Integrity", d.integrity || "Not Available"]]);
  const [q, setQ] = useState(""); const [sec, setSec] = useState("All");
  const total = sections.reduce((n, [, r]) => n + r.length, 0);
  const needle = q.trim().toLowerCase();
  const shown = sections.filter(([n]) => sec === "All" || n === sec)
    .map(([n, rows]) => [n, rows.filter(([k, v]) => !needle || k.toLowerCase().includes(needle) || v.toLowerCase().includes(needle))] as [string, [string, string][]])
    .filter(([, r]) => r.length);
  const all = shown.flatMap(([, r]) => r).map(([k, v]) => `${k}: ${v}`).join("\n");
  const typ = String(d.mime || "").split("/").pop()?.toUpperCase() || "Unknown";
  return (
    <div>
      <div className="mv-head">
        <span className="mv-ico" aria-hidden="true"><svg width="22" height="16" viewBox="0 0 22 16" fill="none" stroke="#00e5ff" strokeWidth="2"><path d="M1 8s4-7 10-7 10 7 10 7-4 7-10 7S1 8 1 8z" /><circle cx="11" cy="8" r="3" /></svg></span>
        <div><h3>File metadata</h3><span className="mono">{d.name} · {total} properties</span></div>
      </div>
      <div className="grid">
        <Stat label="Type" value={typ} sub={d.mime || ""} /><Stat label="Size" value={fmtSize(d.size)} sub="On disk" tone="t" /><Stat label="Properties" value={total} sub={`Across ${sections.length} sections`} tone="m" />
      </div>
      <div className="mv-bar" style={{ marginTop: 16 }}>
        <input className="in" placeholder="Search properties and values" aria-label="Search properties and values" value={q} onChange={(e) => setQ(e.target.value)} />
        <CopyBtn text={all} label="all shown properties" caption="Copy all shown" />
      </div>
      <div className="chips">
        <button className={`chip-b ${sec === "All" ? "on" : ""}`} onClick={() => setSec("All")}>All<i>{total}</i></button>
        {sections.map(([n, r]) => <button key={n} className={`chip-b ${sec === n ? "on" : ""}`} onClick={() => setSec(n)}>{n}<i>{r.length}</i></button>)}
      </div>
      {!shown.length ? <Empty text="No properties match your search." /> : shown.map(([n, rows]) => (
        <div key={n}><h3 className="mv-sec">{n}<i>{rows.length}</i></h3>
          <div className="prop-grid">{rows.map(([k, v]) => <PropRow key={k} k={k} v={v} />)}</div></div>
      ))}
    </div>
  );
}

function DerivedResult({ r }: { r: any }) {
  let diff: Record<string, { old: string; new: string }> | null = null;
  try { const j = JSON.parse(r.derived_note); if (j && typeof j === "object" && !Array.isArray(j)) diff = j; } catch {}
  return (
    <div>
      <p className="ok-msg" role="status">Done. A new copy was created and is being analyzed. Your original file was not changed.</p>
      {diff ? <table><thead><tr><th>Field</th><th>Before</th><th>After</th></tr></thead><tbody>
        {Object.entries(diff).map(([k, v]) => <tr key={k}><td>{k}</td><td className="mono">{v.old}</td><td className="mono">{v.new}</td></tr>)}</tbody></table>
        : r.derived_note && <p className="note">{r.derived_note}</p>}
      <p><a className="btn" href={`${API}/api/evidence/${r.id}/download`} download>Download new copy</a></p>
    </div>
  );
}

function Remover({ sel, setSel }: { sel: number | null; setSel: (n: number) => void }) {
  const { list, err, load } = usePolledList();
  const [busy, setBusy] = useState(false); const [res, setRes] = useState<any>(null); const [msg, setMsg] = useState("");
  const [opts, setOpts] = useState<any>(null); const [pick, setPick] = useState<Record<string, boolean>>({});
  useEffect(() => {
    setRes(null); setMsg(""); setOpts(null); setPick({});
    if (!sel) return;
    api(`/api/evidence/${sel}/removable`).then((r) => setOpts(r)).catch((e) => setMsg(e.message));
  }, [sel]);
  const chosen = list?.find((x) => x.id === sel);
  const items: any[] = opts?.items || []; const keys = items.filter((i) => pick[i.key]).map((i) => i.key);
  const all = items.length > 0 && keys.length === items.length;
  const toggleAll = (on: boolean) => setPick(Object.fromEntries(items.map((i) => [i.key, on])));
  async function run() {
    setBusy(true); setMsg(""); setRes(null);
    try { setRes(await post(`/api/evidence/${sel}/remove-selected`, { keys })); load(); } catch (x: any) { setMsg(x.message); }
    setBusy(false);
  }
  return <>
    <h2>Metadata Remover</h2>
    <Card title="What it does">
      <p className="note">Shows the hidden data a file carries, such as GPS location, camera and device details, author names and comments. Tick only what you want removed, or press Select all to remove everything.
        A clean copy is created. Images keep their pixels and colour profile untouched, and photos keep their rotation. Audio and video are copied without re-encoding. Your original is never changed.</p>
    </Card>
    {err && <div className="err">{err}</div>}
    {!list ? <Skeleton /> : <Card title="Choose evidence"><EvTable list={list} onPick={setSel} label="Select" /></Card>}
    {chosen && <Card title={chosen.name}>
      {!opts && !msg && <Skeleton />}
      {msg && <div className="err" role="alert">{msg}</div>}
      {opts && !items.length && <Empty text="No removable metadata was found in this file. It is already clean." />}
      {items.length > 0 && <>
        <div className="mv-bar">
          <label className="chk"><input type="checkbox" checked={all} onChange={(e) => toggleAll(e.target.checked)} /> <b>Select all ({items.length})</b></label>
          <span className="note">{keys.length} selected</span>
        </div>
        {items.map((i) => <div className="prop" key={i.key}>
          <label className="chk" style={{ margin: 0 }}><input type="checkbox" checked={!!pick[i.key]} onChange={(e) => setPick({ ...pick, [i.key]: e.target.checked })} /> <span className="pk">{i.label}</span></label>
          <span className="pv mono">{i.detail}</span><span />
        </div>)}
        <ul className="note">{(opts.notes || []).map((n: string) => <li key={n}>{n}</li>)}</ul>
        <p><button className="btn" onClick={run} disabled={busy || !keys.length}>{busy ? "Please wait" : all ? "Remove all metadata" : "Remove selected data"}</button></p>
      </>}
      {res && <DerivedResult r={res} />}
    </Card>}
    <BulkClean list={list} reload={load} />
  </>;
}

function BulkClean({ list, reload }: { list: any[] | null; reload: () => void }) {
  const [pick, setPick] = useState<Record<number, boolean>>({}); const [job, setJob] = useState<any>(null); const [msg, setMsg] = useState(""); const [busy, setBusy] = useState(false);
  const rows = (list || []).filter((e) => !e.derived_op && e.status === "completed");
  const ids = rows.filter((e) => pick[e.id]).map((e) => e.id);
  useEffect(() => {
    if (!job || job.status === "completed") return;
    const t = setTimeout(() => api(`/api/bulk/${job.id}`).then((j) => { setJob(j); if (j.status === "completed") reload(); }).catch((e) => setMsg(e.message)), 1500);
    return () => clearTimeout(t);
  }, [job, reload]);
  async function start() {
    setBusy(true); setMsg(""); setJob(null);
    try { setJob(await post("/api/bulk/clean", { ids })); } catch (x: any) { setMsg(x.message); }
    setBusy(false);
  }
  if (!rows.length) return null;
  const running = !!job && job.status !== "completed";
  return <Card title="Clean many files at once">
    <p className="note">Tick the files and start. They are cleaned in the background, so you can keep working. When it is done, download all clean copies as one ZIP.</p>
    <div className="mv-bar">
      <label className="chk"><input type="checkbox" checked={ids.length === rows.length} onChange={(e) => setPick(Object.fromEntries(rows.map((r) => [r.id, e.target.checked])))} /> <b>Select all ({rows.length})</b></label>
      <span className="note">{ids.length} selected</span>
    </div>
    <div style={{ maxHeight: 240, overflow: "auto" }}>{rows.map((e) => <label key={e.id} className="chk"><input type="checkbox" checked={!!pick[e.id]} onChange={(x) => setPick({ ...pick, [e.id]: x.target.checked })} /> {e.name} <span className="note">{fmtSize(e.size)}</span></label>)}</div>
    <p><button className="btn" onClick={start} disabled={busy || running || !ids.length}>{running ? "Cleaning" : "Clean selected files"}</button></p>
    {msg && <div className="err" role="alert">{msg}</div>}
    {job && <div>
      <div className="bar" role="progressbar" aria-valuenow={job.percent} aria-valuemin={0} aria-valuemax={100}><i style={{ width: job.percent + "%" }} /></div>
      <p className="note">{job.percent}% · {job.done} of {job.total} files processed{job.failed ? ` · ${job.failed} could not be cleaned` : ""}</p>
      {job.status === "completed" && <>
        {job.failed > 0 && <ul className="note">{job.results.filter((r: any) => r.error).slice(0, 10).map((r: any) => <li key={r.source}>Evidence #{r.source}: {r.error}</li>)}</ul>}
        {job.done > job.failed && <a className="btn" href={`${API}/api/bulk/${job.id}/download`} download>Download clean ZIP</a>}
      </>}
    </div>}
  </Card>;
}

function Editor({ sel, setSel }: { sel: number | null; setSel: (n: number) => void }) {
  const { list, err, load } = usePolledList();
  const [form, setForm] = useState<any>(null); const [vals, setVals] = useState<Record<string, string>>({}); const [orig, setOrig] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState(""); const [res, setRes] = useState<any>(null); const [busy, setBusy] = useState(false);
  const [rmGps, setRmGps] = useState(false);
  useEffect(() => {
    setForm(null); setRes(null); setMsg(""); setRmGps(false);
    if (!sel) return;
    api(`/api/evidence/${sel}/editable`).then((r) => {
      setForm(r); const o = Object.fromEntries(r.fields.map((f: any) => [f.key, f.value])) as Record<string, string>; setOrig(o); setVals(o);
    }).catch((e) => setMsg(e.message));
  }, [sel]);
  async function save() {
    const changed = Object.fromEntries(Object.entries(vals).filter(([k, v]) => v !== orig[k]));
    if (!Object.keys(changed).length && !rmGps) { setMsg("Change at least one field first."); return; }
    setBusy(true); setMsg(""); setRes(null);
    try { setRes(await post(`/api/evidence/${sel}/edit-metadata`, { fields: changed, remove_gps: rmGps })); load(); } catch (x: any) { setMsg(x.message); }
    setBusy(false);
  }
  const chosen = list?.find((x) => x.id === sel);
  return <>
    <h2>Metadata Editor</h2>
    <Card title="Read this first">
      <p className="note">Editing saves a new copy. The original stays unchanged with its own SHA-256 hash. The new copy is labelled as edited, and the change is written into its report and the security log.
        Do not present an edited copy as the original.</p>
    </Card>
    {err && <div className="err">{err}</div>}
    {!list ? <Skeleton /> : <Card title="Choose evidence"><EvTable list={list} onPick={setSel} label="Select" /></Card>}
    {chosen && <Card title={chosen.name}>
      {!form && !msg && <Skeleton />}
      {msg && <div className="err" role="alert">{msg}</div>}
      {form && <>
        {form.fields.map((f: any) => <Field key={f.key} label={f.label} maxLength={500} value={vals[f.key] ?? ""} onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })} />)}
        {form.can_remove_gps && <label className="chk"><input type="checkbox" checked={rmGps} onChange={(e) => setRmGps(e.target.checked)} /> Also remove the GPS location from this photo</label>}
        <ul className="note">{form.notes.map((n: string) => <li key={n}>{n}</li>)}</ul>
        <p className="note">Clear a field to remove that value.</p>
        <button className="btn" onClick={save} disabled={busy}>{busy ? "Please wait" : "Save as new copy"}</button>
        {res && <DerivedResult r={res} />}
      </>}
    </Card>}
  </>;
}
