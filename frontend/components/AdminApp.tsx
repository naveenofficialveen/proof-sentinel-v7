"use client";
import { useCallback, useEffect, useState } from "react";
import { api, post } from "../lib/api";
import { Badge, Card, Empty, Field, KV, Modal, PasswordField, Skeleton, Stat, fmtDate, fmtSize } from "./ui";

type V = "dashboard" | "users" | "evidence" | "reports" | "logs" | "settings";
const NAV: [V, string][] = [["dashboard", "Dashboard"], ["users", "Users"], ["evidence", "Evidence"], ["reports", "Reports"], ["logs", "Security Logs"], ["settings", "Settings"]];

export default function AdminApp() {
  const [admin, setAdmin] = useState<any>(null); const [boot, setBoot] = useState(true); const [v, setV] = useState<V>("dashboard"); const [askLogout, setAskLogout] = useState(false);
  useEffect(() => { api("/api/admin/me").then(setAdmin).catch(() => {}).finally(() => setBoot(false)); }, []);
  if (boot) return <div className="center"><Skeleton /></div>;
  if (!admin) return <Login onDone={setAdmin} />;
  return <>
    <header className="top"><span className="node"><i />ADMIN SESSION</span><span className="sp" /><span className="who">{admin.username}</span></header>
    <div className="shell">
      <aside className="side">
        {NAV.map(([k, l]) => <button key={k} className={v === k ? "on" : ""} onClick={() => setV(k)}>{l}</button>)}
        <button onClick={() => setAskLogout(true)}>Logout</button>
      </aside>
      <main className="main">{v === "dashboard" ? <Dash /> : v === "users" ? <Users /> : v === "evidence" ? <Ev /> : v === "reports" ? <Reps /> : v === "logs" ? <Logs /> : <SettingsView />}</main>
    </div>
    <Modal open={askLogout} onClose={() => setAskLogout(false)}>
      <h3>Confirm logout</h3>
      <p>Are you sure you want to log out of the admin console? You will need to sign in again to manage users and evidence.</p>
      <div className="acts">
        <button className="btn ghost" onClick={() => setAskLogout(false)}>Stay signed in</button>
        <button className="btn danger" onClick={async () => { await post("/api/admin/logout").catch(() => {}); setAskLogout(false); setAdmin(null); }}>Yes, log out</button>
      </div>
    </Modal>
  </>;
}

function Login({ onDone }: { onDone: (a: any) => void }) {
  const [u, setU] = useState(""); const [p, setP] = useState(""); const [show, setShow] = useState(false); const [err, setErr] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    try { await post("/api/admin/login", { username: u, password: p }); onDone(await api("/api/admin/me")); } catch (x: any) { setErr(x.message); }
  }
  return <div className="center"><Card title="Admin sign in"><form onSubmit={submit}>
    <Field label="Admin email or username" required value={u} onChange={(e) => setU(e.target.value)} />
    <Field label="Password" type={show ? "text" : "password"} required value={p} onChange={(e) => setP(e.target.value)} />
    <label className="note"><input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} /> Show password</label>
    {err && <div className="err" role="alert">{err}</div>}<p><button className="btn">Admin Login</button></p>
  </form></Card></div>;
}

function Dash() {
  const [s, setS] = useState<any>(null);
  useEffect(() => { api("/api/admin/stats").then(setS).catch(() => {}); }, []);
  if (!s) return <Skeleton />;
  const bars: [string, number][] = [["Users", s.users], ["Files", s.files], ["Images", s.images], ["Videos", s.videos], ["Processed", s.processed], ["Reports", s.reports]];
  const max = Math.max(1, ...bars.map((b) => b[1]));
  return <><h2>Dashboard</h2><div className="grid">
    <Stat label="Registered users" value={s.users} /><Stat label="Active users" value={s.active_users} /><Stat label="Locked users" value={s.locked_users} />
    <Stat label="Uploaded files" value={s.files} /><Stat label="Uploaded images" value={s.images} /><Stat label="Uploaded videos" value={s.videos} />
    <Stat label="Processed evidence" value={s.processed} /><Stat label="Generated reports" value={s.reports} /></div>
    <Card title="Overview"><div className="chart">{bars.map(([l, n]) => <div key={l}><i style={{ height: (n / max) * 90 + 2 }} />{l} ({n})</div>)}</div></Card></>;
}

function Users() {
  const [q, setQ] = useState(""); const [rows, setRows] = useState<any[] | null>(null); const [detail, setDetail] = useState<any>(null); const [confirm, setConfirm] = useState<any>(null);
  const load = useCallback(() => api(`/api/admin/users?q=${encodeURIComponent(q)}`).then(setRows).catch(() => setRows([])), [q]);
  useEffect(() => { load(); }, [load]);
  async function toggle() {
    await post(`/api/admin/users/${confirm.id}/${confirm.status === "LOCKED" ? "unlock" : "lock"}`);
    setConfirm(null); load(); if (detail) setDetail(await api(`/api/admin/users/${detail.id}`));
  }
  const actions = (u: any) => <button className={`btn ${u.status === "LOCKED" ? "" : "danger"}`} onClick={() => setConfirm(u)}>{u.status === "LOCKED" ? "Unlock User" : "Lock User"}</button>;
  return <><h2>Users</h2>
    <input className="in" placeholder="Search by name or email" aria-label="Search users" value={q} onChange={(e) => setQ(e.target.value)} />
    <Card>{!rows ? <Skeleton /> : !rows.length ? <Empty text="No users found." /> : <table><thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Registered</th><th>Status</th><th>Files</th><th>Last activity</th><th /></tr></thead><tbody>
      {rows.map((u) => <tr key={u.id}><td>{u.id}</td><td>{u.name}</td><td>{u.email}</td><td>{fmtDate(u.created_at)}</td><td><Badge s={u.status} /></td><td>{u.files}</td><td>{fmtDate(u.last_activity)}</td>
        <td><button className="btn ghost" onClick={async () => setDetail(await api(`/api/admin/users/${u.id}`))}>View User</button> {actions(u)}</td></tr>)}</tbody></table>}</Card>
    <Modal open={!!detail} onClose={() => setDetail(null)}>{detail && <>
      <h3>{detail.name}</h3><KV rows={[["Email", detail.email], ["Status", detail.status], ["Registered", fmtDate(detail.created_at)], ["Last activity", fmtDate(detail.last_activity)],
        ["Uploaded files", detail.files], ["Images", detail.images], ["Videos", detail.videos]]} />
      <h3 style={{ marginTop: 14 }}>Analysis history</h3>{detail.analysis_history.length ? detail.analysis_history.map((a: any) => <div key={a.id}>{a.name} <Badge s={a.status} /></div>) : <Empty text="No analyses yet." />}
      <h3 style={{ marginTop: 14 }}>Report history</h3>{detail.report_history.length ? detail.report_history.map((r: any) => <div key={r.id}>Report {r.id} for evidence {r.evidence_id}, {fmtDate(r.created_at)}</div>) : <Empty text="No reports yet." />}
      <p>{actions(detail)} <button className="btn ghost" onClick={() => setDetail(null)}>Close</button></p></>}</Modal>
    <Modal open={!!confirm} onClose={() => setConfirm(null)}>{confirm && <>
      <h3>{confirm.status === "LOCKED" ? "Unlock" : "Lock"} {confirm.email}?</h3>
      <p>{confirm.status === "LOCKED" ? "The user will be able to sign in and use the system again." : "The user will be blocked from all protected features immediately."}</p>
      <button className="btn" onClick={toggle}>{confirm.status === "LOCKED" ? "Unlock User" : "Lock User"}</button> <button className="btn ghost" onClick={() => setConfirm(null)}>Cancel</button></>}</Modal></>;
}

function Ev() {
  const [f, setF] = useState({ q: "", category: "", status: "", sort: "created_at", order: "desc" }); const [rows, setRows] = useState<any[] | null>(null);
  useEffect(() => { api("/api/admin/evidence?" + new URLSearchParams(f)).then(setRows).catch(() => setRows([])); }, [f]);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return <><h2>Evidence monitoring</h2>
    <div className="grid">
      <input className="in" placeholder="Search file or user" aria-label="Search" value={f.q} onChange={set("q")} />
      <select aria-label="Category" value={f.category} onChange={set("category")}><option value="">All types</option>{["image", "video", "audio", "pdf", "office_xml", "office_legacy", "text", "archive", "unknown"].map((c) => <option key={c}>{c}</option>)}</select>
      <select aria-label="Status" value={f.status} onChange={set("status")}><option value="">All statuses</option>{["queued", "analyzing", "completed", "failed"].map((c) => <option key={c}>{c}</option>)}</select>
      <select aria-label="Sort" value={f.sort} onChange={set("sort")}><option value="created_at">Upload date</option><option value="size">Size</option><option value="name">Name</option><option value="status">Status</option></select>
      <select aria-label="Order" value={f.order} onChange={set("order")}><option value="desc">Descending</option><option value="asc">Ascending</option></select></div>
    <Card>{!rows ? <Skeleton /> : !rows.length ? <Empty text="No evidence matches these filters." /> : <table><thead><tr><th>File</th><th>User</th><th>Type</th><th>Size</th><th>Uploaded</th><th>Processing</th><th>Verification</th><th>Signature</th></tr></thead><tbody>
      {rows.map((e) => <tr key={e.id}><td>{e.name}</td><td>{e.user}</td><td>{e.category || "Pending"}</td><td>{fmtSize(e.size)}</td><td>{fmtDate(e.created_at)}</td><td><Badge s={e.status} /></td><td>{e.verification || "Not Available"}</td><td>{e.signature || "Not Available"}</td></tr>)}</tbody></table>}</Card></>;
}

function Reps() {
  const [rows, setRows] = useState<any[] | null>(null);
  useEffect(() => { api("/api/admin/reports").then(setRows).catch(() => setRows([])); }, []);
  return <><h2>Report monitoring</h2><Card>{!rows ? <Skeleton /> : !rows.length ? <Empty text="No reports generated yet." /> : <table><thead><tr><th>Report</th><th>Evidence</th><th>User</th><th>Analysis</th><th>Generated</th></tr></thead><tbody>
    {rows.map((r) => <tr key={r.id}><td>{r.id}</td><td>{r.file}</td><td>{r.user}</td><td><Badge s={r.analysis_status} /></td><td>{fmtDate(r.created_at)}</td></tr>)}</tbody></table>}</Card></>;
}

function Logs() {
  const [rows, setRows] = useState<any[] | null>(null); const [ev, setEv] = useState("");
  useEffect(() => { api(`/api/admin/logs?event=${encodeURIComponent(ev)}`).then(setRows).catch(() => setRows([])); }, [ev]);
  return <><h2>Security logs</h2>
    <select aria-label="Event" value={ev} onChange={(e) => setEv(e.target.value)}><option value="">All events</option>
      {["LOGIN", "LOGIN_FAILED", "LOGIN_BLOCKED_LOCKED", "LOGOUT", "SIGNUP", "UPLOAD", "ANALYSIS_DONE", "ANALYSIS_FAILED", "REPORT_GENERATED", "REPORT_DOWNLOAD", "FILE_DOWNLOAD", "METADATA_REMOVED", "METADATA_EDITED", "PASSWORD_OTP_SENT", "PASSWORD_OTP_NOT_SENT", "PASSWORD_OTP_FAILED", "PASSWORD_OTP_UNKNOWN_EMAIL", "PASSWORD_RESET_DONE", "BULK_CLEAN_START", "BULK_CLEAN_DONE", "BULK_DOWNLOAD", "GEO_LOOKUP", "ADMIN_PASSWORD_CHANGED", "ADMIN_PASSWORD_CHANGE_FAILED", "USER_LOCKED", "USER_UNLOCKED", "ADMIN_LOGIN", "ADMIN_LOGIN_FAILED", "ADMIN_LOGOUT"].map((e) => <option key={e}>{e}</option>)}</select>
    <Card>{!rows ? <Skeleton /> : !rows.length ? <Empty text="No events recorded." /> : <table><thead><tr><th>Time</th><th>Actor</th><th>Event</th><th>Detail</th></tr></thead><tbody>
      {rows.map((l) => <tr key={l.id}><td>{fmtDate(l.created_at)}</td><td>{l.actor_type}{l.actor_id ? ` #${l.actor_id}` : ""}</td><td>{l.event}</td><td>{l.detail || ""}</td></tr>)}</tbody></table>}</Card></>;
}

function SettingsView() {
  const [info, setInfo] = useState<any>(null);
  useEffect(() => { api("/api/admin/mail").then(setInfo).catch(() => {}); }, []);
  return <><h2>Settings</h2>
    <PasswordCard />
    <Card title="E-mail for forgot-password codes">
      {!info ? <Skeleton /> : <KV rows={[["Status", info.configured ? "Configured" : "Not configured"], ["Mail server", `${info.host || "Not set"}:${info.port}`], ["Sender account", info.user || "Not set"], ["From address", info.from || "Not set"]]} />}
      {info && !info.configured && <p className="warn-box">Fill SMTP_USER, SMTP_PASSWORD and SMTP_FROM in the .env file (for Gmail, use a 16-character App Password), then restart the containers.</p>}
    </Card></>;
}

function PasswordCard() {
  const [cur, setCur] = useState(""); const [n1, setN1] = useState(""); const [n2, setN2] = useState("");
  const [res, setRes] = useState<{ ok: boolean; message: string } | null>(null); const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setRes(null);
    if (n1 !== n2) { setRes({ ok: false, message: "The two new passwords do not match." }); return; }
    setBusy(true);
    try { const r = await post("/api/admin/change-password", { current_password: cur, new_password: n1 }); setRes({ ok: true, message: r.message }); setCur(""); setN1(""); setN2(""); }
    catch (x: any) { setRes({ ok: false, message: x.message }); }
    setBusy(false);
  }
  return <Card title="Change admin password"><form onSubmit={submit}>
    <PasswordField label="Current password" required autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} />
    <PasswordField label="New password (at least 10 characters)" required minLength={10} autoComplete="new-password" value={n1} onChange={(e) => setN1(e.target.value)} />
    <PasswordField label="Confirm new password" required minLength={10} autoComplete="new-password" value={n2} onChange={(e) => setN2(e.target.value)} />
    <button className="btn" disabled={busy}>{busy ? "Please wait" : "Change password"}</button>
    {res && <p className={res.ok ? "ok-msg" : "err"} role="status">{res.message}</p>}
  </form></Card>;
}
