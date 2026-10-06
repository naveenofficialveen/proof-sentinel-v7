"use client";
import { useState } from "react";
import { api, API } from "../lib/api";
import { Badge, Card, CopyBtn, Empty, KV, Stat } from "./ui";

const TABS: [string, string][] = [
  ["social", "Social-media trace"], ["magic", "File type check"], ["ela", "Tamper heat-map"], ["doc", "Document lock"], ["map", "Location & privacy"],
  ["gauge", "Quality gauge"], ["size", "Size check"], ["name", "File name"], ["hex", "Hex markers"],
];
const none = (t: string) => <Empty text={t} />;

function Gauge({ score, tone }: { score: number; tone: string }) {
  const a = Math.PI * (1 - score / 100); const cx = 120, cy = 110, r = 90;
  const col = tone === "ok" ? "#2de2a6" : tone === "warn" ? "#ffb84d" : "#ff7a6e";
  const pt = (t: number, k: number) => `${cx + k * Math.cos(Math.PI * (1 - t))},${cy - k * Math.sin(Math.PI * (1 - t))}`;
  return (
    <svg viewBox="0 0 240 140" width="100%" style={{ maxWidth: 320 }} role="img" aria-label={`Integrity gauge ${score} out of 100`}>
      <path d={`M ${pt(0, r)} A ${r} ${r} 0 0 1 ${pt(1, r)}`} fill="none" stroke="#252c3a" strokeWidth="16" />
      <path d={`M ${pt(0, r)} A ${r} ${r} 0 0 1 ${pt(score / 100, r)}`} fill="none" stroke={col} strokeWidth="16" />
      {[0, 25, 50, 75, 100].map((t) => <line key={t} x1={pt(t / 100, r - 22).split(",")[0]} y1={pt(t / 100, r - 22).split(",")[1]} x2={pt(t / 100, r - 12).split(",")[0]} y2={pt(t / 100, r - 12).split(",")[1]} stroke="#6b768c" strokeWidth="2" />)}
      <line x1={cx} y1={cy} x2={cx + (r - 28) * Math.cos(a)} y2={cy - (r - 28) * Math.sin(a)} stroke="#e8edf7" strokeWidth="4" strokeLinecap="round" />
      <circle cx={cx} cy={cy} r="7" fill="#e8edf7" />
      <text x={cx} y={cy + 28} textAnchor="middle" fontSize="22" fontWeight="700" fill={col}>{score}</text>
    </svg>
  );
}

function Heat({ id }: { id: number }) {
  const [on, setOn] = useState(true); const [op, setOp] = useState(70); const [bad, setBad] = useState(false);
  return (
    <div>
      <div style={{ position: "relative", maxWidth: 760 }}>
        <img src={`${API}/api/evidence/${id}/preview.jpg`} alt="Original picture" style={{ display: "block", width: "100%" }} onError={() => setBad(true)} />
        {on && !bad && <img src={`${API}/api/evidence/${id}/ela.png`} alt="Red heat layer where compression differs" onError={() => setBad(true)}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: op / 100, pointerEvents: "none" }} />}
      </div>
      {bad ? <p className="err">The heat layer could not be loaded for this picture.</p> : <div className="mv-bar" style={{ marginTop: 12 }}>
        <label className="chk"><input type="checkbox" checked={on} onChange={(e) => setOn(e.target.checked)} /> Show red heat layer</label>
        <label className="chk">Strength <input type="range" min={10} max={100} value={op} onChange={(e) => setOp(+e.target.value)} /></label>
      </div>}
    </div>
  );
}

function MapBox({ id, geo }: { id: number; geo: { lat: number; lon: number } }) {
  const [place, setPlace] = useState<string>(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const d = 0.01; const bbox = `${geo.lon - d},${geo.lat - d},${geo.lon + d},${geo.lat + d}`;
  async function look() {
    setBusy(true); setErr("");
    try { setPlace((await api(`/api/evidence/${id}/place`)).name); } catch (x: any) { setErr(x.message); }
    setBusy(false);
  }
  return (
    <div>
      <div style={{ maxWidth: 760 }}>
        <iframe title="Map of the photo position" loading="lazy" referrerPolicy="no-referrer" style={{ width: "100%", height: 300, border: "1px solid var(--line)", background: "#111" }}
          src={`https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${geo.lat},${geo.lon}`} />
      </div>
      <p className="note">GPS detected. The map is loaded from OpenStreetMap. If your browser blocks the embedded map, use <a href={`https://www.openstreetmap.org/?mlat=${geo.lat}&mlon=${geo.lon}#map=16/${geo.lat}/${geo.lon}`} target="_blank" rel="noreferrer">Open full map</a>.</p>
      <KV rows={[["Latitude", geo.lat.toFixed(6)], ["Longitude", geo.lon.toFixed(6)], ["Place name", place || "Not looked up yet"]]} />
      <p><button className="btn ghost sm" disabled={busy} onClick={look}>{busy ? "Looking up" : "Find place name"}</button>{" "}
        <a className="btn ghost sm" target="_blank" rel="noreferrer" href={`https://www.openstreetmap.org/?mlat=${geo.lat}&mlon=${geo.lon}#map=16/${geo.lat}/${geo.lon}`}>Open full map</a></p>
      <p className="note">Find place name sends these coordinates to OpenStreetMap Nominatim, so it only runs when you press the button.</p>
      {err && <div className="err" role="alert">{err}</div>}
    </div>
  );
}

export default function Forensics({ d }: { d: any }) {
  const f = d.metadata?.forensics; const [tab, setTab] = useState("social");
  if (!f) return null;
  if (f.error) return <Card title="Forensic checks"><div className="err">{f.error}</div></Card>;
  const img = d.category === "image"; const jpeg = d.mime === "image/jpeg";
  const T = (rows: [string, any][]) => <KV rows={rows.map(([k, v]) => [k, v === null || v === undefined || v === "" ? "Not Available" : String(v)] as [string, string])} />;
  const lock = f.doc_lock;

  return <Card title="Forensic checks" right={<span className="note">Indicators, not proof</span>}>
    <div className="tabs">{TABS.filter(([k]) => k === "magic" || k === "name" || img).map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}</div>

    {tab === "social" && (!f.social ? none("Social-media tracing applies to pictures.") : <>
      <div className="grid"><Stat label="Verdict" value={f.social.verdict} tone={f.social.score >= 4 ? "m" : "c"} sub={f.social.likely_source ? `Likely source: ${f.social.likely_source}` : undefined} />
        {f.dqt && <Stat label="JPEG quality (from tables)" value={f.dqt.ijg_quality ?? "n/a"} sub={f.dqt.exact ? "Standard table" : "Custom table"} tone="t" />}
        {f.dqt && <Stat label="Quantisation fingerprint" value={f.dqt.luma_fingerprint || "n/a"} sub={f.dqt.subsampling ? `Chroma ${f.dqt.subsampling}` : undefined} />}</div>
      {f.dqt && <><h3 className="mv-sec">Compression fingerprint (DQT)</h3><p className="note">{f.dqt.classification}</p>
        {f.dqt.luma_first_row && <p className="mono">First row of the luminance table: {f.dqt.luma_first_row.join(", ")} <CopyBtn text={f.dqt.luma_first_row.join(", ")} label="table row" /></p>}</>}
      <h3 className="mv-sec">Why this verdict</h3>
      {f.social.reasons.length ? <ul className="note">{f.social.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul> : <p className="note">Nothing in this file points to a messaging app.</p>}
      <p className="note">{f.social.note}</p></>)}

    {tab === "magic" && (!f.magic ? none("Not available.") : <>
      <div className="grid"><Stat label="Verdict" value={f.magic.verdict} tone={f.magic.blocked ? undefined : "m"} sub={f.magic.detected_type} /></div>
      <p className={f.magic.blocked ? "err" : f.magic.verdict === "OK" ? "ok-msg" : "note"} role="status">{f.magic.message}</p>
      {f.magic.double_extension && <p className="err">The name has a double extension, a trick used to hide the real type.</p>}
      {T([["Extension in name", "." + f.magic.extension], ["Detected from content", f.magic.detected_type], ["First 16 bytes (hex)", f.magic.header_hex]])}
      <p className="note">Known signatures: FF D8 FF = JPEG, 89 50 4E 47 = PNG, 25 50 44 46 = PDF, 50 4B 03 04 = ZIP/DOCX/XLSX, 4D 5A = Windows program. The file is only read, never run.</p></>)}

    {tab === "ela" && (!jpeg ? none("Error Level Analysis works on JPEG pictures.") : !f.ela || f.ela.error ? none("ELA could not run on this file.") : <>
      <div className="grid"><Stat label="Result" value={String(f.ela.level || "n/a").toUpperCase()} tone={f.ela.level === "high" ? undefined : "m"} sub="Edit suspicion" />
        <Stat label="Unusual area" value={`${f.ela.hot_area_percent ?? 0}%`} sub="Of the picture" tone="t" /><Stat label="Peak error" value={f.ela.peak_error ?? "n/a"} sub="Highest level" /></div>
      <p className={f.ela.level === "high" ? "warn-box" : "note"}>{f.ela.verdict}</p>
      {f.ela.hot_region && <p className="note">Strongest area: about {f.ela.hot_region.x}% from the left and {f.ela.hot_region.y}% from the top, {f.ela.hot_region.w}% wide and {f.ela.hot_region.h}% tall.</p>}
      <Heat id={d.id} />
      <p className="note">Red marks areas that react differently when the picture is saved again. Cropped, resized or heavily shared pictures can light up without any edit, so use this as a lead and judge by eye.</p></>)}

    {tab === "doc" && ((!lock || lock.status === "not_applicable" || lock.status === "ocr_failed") ?
      none(lock?.reason || "No readable document text was found. This check needs a photo or scan of a document with printed text such as a name and an ID number.") : <>
      {lock.status === "altered" && <div className="err" role="alert"><b>Document Altered</b> The ID numbers match an earlier document, but other details differ.</div>}
      {lock.status === "match" && <p className="ok-msg" role="status">Matches an earlier locked document. No change in the locked fields.</p>}
      {lock.status === "locked" && <p className="note">This document is now locked. If you upload another copy later, its text is compared with this one.</p>}
      {T([["Name read", lock.name_guess], ["ID numbers read", (lock.ids || []).join(", ") || "None found"], ["Numbers counted", lock.number_count], ["Lock code (SHA-256 of ID and number fields)", lock.fields_sha256], ["Full text fingerprint (SHA-256)", lock.text_sha256]])}
      {(lock.compared || []).map((c: any) => <div key={c.evidence_id} style={{ marginTop: 10 }}><b>Evidence #{c.evidence_id}</b> {c.name} <Badge s={c.result === "altered" ? "failed" : "completed"} />
        {c.differences?.length > 0 && <ul className="note">{c.differences.map((x: string) => <li key={x}>{x}</li>)}</ul>}</div>)}
      <p className="note">OCR can misread blurry text, so a mismatch is a warning to check the two pictures, not a verdict. Only text read by OCR is locked.</p></>)}

    {tab === "map" && <>
      {f.geo ? <MapBox id={d.id} geo={f.geo} /> : none("This file has no GPS position.")}
      {f.privacy && <><h3 className="mv-sec">Privacy score</h3>
        <div className="grid"><Stat label="Score" value={`${f.privacy.score}/100`} sub={f.privacy.level} tone={f.privacy.score >= 80 ? "m" : "c"} /></div>
        <table><thead><tr><th>Item</th><th>In this file</th><th>Points lost</th></tr></thead><tbody>
          {f.privacy.items.map((i: any) => <tr key={i.item}><td>{i.item}</td><td>{i.present ? "Yes" : "No"}</td><td>{i.present ? i.points : 0}</td></tr>)}</tbody></table>
        <p className="note">100 means nothing personal is stored. Use the Metadata Remover to raise the score.</p></>}</>}

    {tab === "gauge" && (!f.quality || f.quality.error ? none("Quality could not be measured for this file.") : <>
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap", alignItems: "center" }}>
        <Gauge score={f.quality.score} tone={f.quality.tone} />
        <div><div className="stat"><span className="lbl">Integrity gauge</span><b className={f.quality.tone === "ok" ? "m" : "c"}>{f.quality.label}</b>
          <small>Edge sharpness (Laplacian variance): {f.quality.laplacian_variance}{f.quality.jpeg_quality ? ` · JPEG quality ${f.quality.jpeg_quality}` : ""}</small></div></div>
      </div>
      <p className="note">{f.quality.note}</p></>)}

    {tab === "size" && (!f.size_check || f.size_check.error ? none("Size check is not available.") : <>
      <p className={f.size_check.anomaly ? "warn-box" : "ok-msg"} role="status">{f.size_check.message}</p>
      {T([["Dimensions", `${f.size_check.width} x ${f.size_check.height}`], ["Megapixels", f.size_check.megapixels], ["Aspect ratio", f.size_check.aspect_ratio], ["Matches camera sensor", f.size_check.matches_sensor || "No"],
        ["Dimensions in EXIF", f.size_check.exif_dimensions], ["Size used by an app", f.size_check.social_size_hint]])}</>)}

    {tab === "name" && (!f.filename ? none("Not available.") : <>
      <div className="grid"><Stat label="Pattern" value={f.filename.matched ? f.filename.pattern : "Unknown"} tone={f.filename.family === "social" ? "m" : "c"} sub={f.filename.family ? `Type: ${f.filename.family}` : undefined} /></div>
      {T([["File name", f.filename.name], ["Date in the name", f.filename.date]])}
      {[...(f.filename.flags || []).map((x: string) => [x, true]), ...(f.filename.notes || []).map((x: string) => [x, false])].map(([x, w]: any) => <p key={x} className={w ? "err" : "note"}>{x}</p>)}
      <p className="note">The name can be changed by anyone. It is a hint about where the file came from.</p></>)}

    {tab === "hex" && (!f.hex ? none("Hex marker parsing is available for JPEG and PNG pictures.") : <>
      {T([["First 16 bytes (hex)", f.hex.header_hex], ["End-of-image marker", f.hex.eoi_offset], ["Extra bytes after the image", f.hex.trailing_bytes]])}
      <h3 className="mv-sec">App and software tags found in the raw bytes<i>{f.hex.software_strings.length}</i></h3>
      {f.hex.software_strings.length ? <table><thead><tr><th>Text</th><th>Times</th><th>First at</th></tr></thead><tbody>{f.hex.software_strings.map((s: any) => <tr key={s.text}><td>{s.text}</td><td>{s.count}</td><td className="mono">{s.first_offset}</td></tr>)}</tbody></table> : <p className="note">No known software or app tag was found inside the file.</p>}
      {f.hex.comments?.length > 0 && <><h3 className="mv-sec">Comment segments</h3>{f.hex.comments.map((c: string, i: number) => <pre key={i}>{c}</pre>)}</>}
      <h3 className="mv-sec">Structure markers<i>{f.hex.markers.length}</i></h3>
      <table><thead><tr><th>Offset</th><th>Marker</th><th>Bytes</th><th>Content</th></tr></thead><tbody>{f.hex.markers.map((m: any, i: number) => <tr key={i}><td className="mono">{m.offset}</td><td>{m.marker}</td><td>{m.length}</td><td className="mono">{m.info}</td></tr>)}</tbody></table></>)}
  </Card>;
}
