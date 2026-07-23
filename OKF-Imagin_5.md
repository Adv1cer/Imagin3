# OKF — โครงการ Imagin

> **ที่มาจาก**: `สรุปโครงการ Imagin หลังรวบรวม Context ทั้งหมด`
> 
> **ระบบ**: Imagin — On-Premise AI Design and Image Generation Platform
> **กำลังคนเป้าหมาย POC**: 1 คน + AI-assisted coding / ระยะเวลาเป้าหมาย: 2 เดือน (production scale เดิม 3 คน / 5–8 เดือน ถูกเลื่อนไปเป็น roadmap หลัง POC ผ่าน — ดู §9.2)
> **ผู้ใช้เป้าหมาย POC**: ตัวเองหรือกลุ่มเล็กเท่านั้น ไม่ใช่ 20,000 คนทั้งมหาวิทยาลัย
> **สถานะปัจจุบัน**: Optimize & Update phase — ต่อยอดจาก ComfyUI pipeline ที่ orchestrate ด้วย Ollama (Qwen2.5-VL-32B) ซึ่งสร้างไว้แล้ว กำลังพิสูจน์ capability เพิ่มเติม (Thai poster/infographic, image reference editing) พร้อม deployment split ใหม่
> **แพลตฟอร์มหลัก**: Control Plane บน Local PC + Compute Plane บน DGX Spark (unified memory 128 GB) เชื่อมผ่าน private network
> **อัปเดตล่าสุด**: 2026-07-22 — ดู §10 สำหรับสรุปการเปลี่ยนแปลง

---

## 1. Objective (วัตถุประสงค์หลัก)

### O1 — สร้างระบบออกแบบภาพ AI บน premise ที่รับ prompt ภาษาธรรมชาติและสร้างโปสเตอร์/อินโฟกราฟิกพร้อมใช้
ระบบต้องเข้าใจ intent, ค้นคว้าข้อมูล, วางแผนงานออกแบบ, สร้างภาพ, ประกอบองค์ประกอบ (text / logo / QR / กราฟ) และส่งมอบผลงานที่ผ่านการตรวจ QA + Human review ก่อน export

### O2 — รักษาความถูกต้องและความน่าเชื่อถือของแบรนด์ในทุก output
ทุก factual claim ต้องมีแหล่งอ้างอิงที่ตรวจสอบได้ โลโก้และ brand assets ต้องมาจาก verified registry ที่สามารถ discover จาก official web ได้ ข้อความภาษาไทยต้อง render ถูกต้อง QR ต้องสแกนได้ ไม่มี fake logo หรือ generated body text ใน final output ระบบต้องแยก candidate จาก scraping ออกจาก asset ที่พร้อมใช้งานจริง

### O3 — ทำให้ระบบทำงานได้จริงบน DGX Spark (compute plane) โดยไม่ต้องพึ่ง external API เป็นหลัก
บริหาร lifecycle ของโมเดลบน DGX Spark ให้ไม่ OOM จัดคิว GPU รองรับ planning (LLM) และ image generation/editing บน DGX ส่วน research, orchestration, compositing, QA รันบน local PC (control plane) เชื่อมกันผ่าน private network โดยใช้ external service เฉพาะกรณีที่แจ้งผู้ใช้และได้รับอนุญาต

### O4 — สร้างประสบการณ์ผู้ใช้ที่โปร่งใส ตรวจสอบได้ และแก้ไขง่าย
ผู้ใช้เห็นขั้นตอนการทำงาน แหล่งข้อมูล ตัวเลือก candidate สามารถแก้ copy, regenerate เฉพาะส่วน และ approve ก่อน export ทั้งหมดผ่านแชท — "เลื่อนวางเล็กน้อย" ด้วยมือ (manual reposition) เลื่อนเป็นเป้าหมาย production หลัง POC (ดู §5)

---

## 2. Key Results (ตัวชี้วัดความสำเร็จ)

### KR ของ O1 — ระบบสร้างงานออกแบบอัตโนมัติ
| ID | Key Result | เป้าหมาย |
|---|---|---|
| O1-KR1 | รองรับโหมด `poster` และ `general_image` ใน MVP | 100% |
| O1-KR2 | รองรับโหมด `infographic` ใน MVP หรือ Phase ถัดไป | MVP หรือ Phase 2 |
| O1-KR3 | สร้าง 2–3 candidates ต่อ 1 prompt | ≥ 2 candidates |
| O1-KR4 | รองรับขนาด poster แนวตั้ง 1024×1536 และ 1080×1350 | 100% |
| O1-KR5 | มี 5–8 templates สำหรับ poster | 5–8 templates |
| O1-KR6 | Export ได้ PNG, JPEG และ design JSON | 3 formats |
| O1-KR7 | End-to-end pipeline ทำงานครบหนึ่งรอบจาก prompt ถึง review UI | 1 round |
| O1-KR8 | รองรับโหมด `image_edit` — รับภาพอ้างอิง 2 ภาพ + text instruction เพื่อ swap/แก้องค์ประกอบระหว่างภาพ ผ่าน Qwen-Image-Edit | POC (Phase 0) |

### KR ของ O2 — ความถูกต้องและความน่าเชื่อถือ
| ID | Key Result | เป้าหมาย |
|---|---|---|
| O2-KR1 | ข้อความ final ตรงกับ input 100% | 100% |
| O2-KR2 | QR code ทุกอันสแกนได้และ URL ตรง | 100% |
| O2-KR3 | Logo ที่ใช้ผ่าน verification และไม่ถูก generate | 100% |
| O2-KR4 | Factual claim ทุกข้อมี source และ confidence ≥ 0.90 จึงใช้ | 100% |
| O2-KR5 | ไม่มี unsupported factual claim ใน final output | 0 |
| O2-KR6 | Text overflow ใน final output | 0 |
| O2-KR7 | Fake logo หรือ fake writing ใน accepted output | 0 |
| O2-KR8 | Brand Pack ที่ใช้มาจาก verified registry หรือ provisional + human approve | 100% |
| O2-KR9 | Official domain และ organization identity ถูกต้องก่อนสร้าง Brand Pack | 100% |
| O2-KR10 | Source snapshot ของ brand asset ถูกเก็บไว้พร้อม content hash | 100% |
| O2-KR11 | Asset ที่เคย approve ไม่ถูก overwrite ทันทีเมื่อ source เปลี่ยน แต่ตั้งสถานะ review_required | 100% |

### KR ของ O3 — ทำงานได้บน DGX Spark
| ID | Key Result | เป้าหมาย |
|---|---|---|
| O3-KR1 | Image generation ไม่ OOM บน DGX Spark (owned by Compute Gateway) | 0 OOM |
| O3-KR2 | มี GPU queue และ model lifecycle management บน Compute Gateway (DGX-side) | 1 queue |
| O3-KR3 | ไม่โหลด LLM planning (Qwen3-30B), image generation (Qwen-Image), และ image editing (Qwen-Image-Edit) พร้อมกันเกินกว่าที่ unified memory รองรับ | 0 conflict |
| O3-KR4 | Image generation concurrency จำกัดที่ 1 ใน MVP | 1 |
| O3-KR5 | ระบบทำงาน on-premise / private network โดยไม่ต้อง external API เป็นค่าเริ่มต้น (DGX ที่เข้าถึงผ่าน VPN นับเป็น on-premise) | 100% on-premise default |
| O3-KR6 | บันทึก model hash, seed, workflow version ทุก output | 100% |
| O3-KR7 | Control plane (local PC) reconcile job state ได้หลัง restart/disconnect โดยอ้างอิง PostgreSQL + job UUID ไม่พึ่ง in-memory state | ≥ 95% recovery |

### KR ของ O4 — ประสบการณ์ผู้ใช้โปร่งใสและแก้ไขง่าย
| ID | Key Result | เป้าหมาย |
|---|---|---|
| O4-KR1 | ผู้ใช้เห็นสถานะงานแบบ real-time (SSE/WebSocket) | 100% |
| O4-KR2 | ผู้ใช้เห็นแหล่งที่มาของข้อมูล (sources panel) | 100% |
| O4-KR3 | ผู้ใช้เลือก candidate และแก้ copy ได้ | 100% |
| O4-KR4 | ผู้ใช้ regenerate เฉพาะส่วนได้ | 100% |
| O4-KR5 | Human review ก่อน export | 100% |
| O4-KR6 | Poster accepted โดยไม่ต้องแก้ใหญ่ | ≥ 75% |
| O4-KR7 | Human design rating เฉลี่ย | ≥ 4/5 |
| O4-KR8 | หน้า Create เป็น chat-first โดย default — ไม่บังคับเลือก Mode/Template/Research depth/Palette ก่อนเริ่ม, ค่าเหล่านี้มาจาก AI Planning inference และแสดงเป็น inline summary ที่ override ได้ | 100% |

---

## 3. Final Deliverables (ผลงานสุดท้าย)

### F1 — ซอฟต์แวร์ระบบ

**Control Plane — Local PC** (dev/POC ปัจจุบัน; ย้ายไป on-prem VM เดิมโค้ดไม่เปลี่ยนตอนขึ้น production จริงกับผู้ใช้ ~20,000 คน)
- **Frontend**: Next.js App Router + TypeScript + Tailwind CSS + Shadcn UI
  - **Shell — chatbot-based (ไม่ใช่ dashboard)**: sidebar ซ้าย = New Chat + ประวัติแชท (~10 รายการล่าสุด) + Settings/Logout ด้านล่าง — ตัด nav แยก (Dashboard, Create, Brand Registry, History) ออกทั้งหมด รวมเป็น chat thread เดียวต่อ 1 งาน
  - **ไม่มี sidebar ขวาแบบ Properties/Layers/Export panel** — ผลลัพธ์ (poster/infographic) แสดงเป็นรูปใน conversation thread พร้อม inline action ใต้รูป: Approve, Regenerate (แนบ feedback text), Edit copy, Export (เลือก format ผ่าน dropdown เล็ก ไม่ใช่ panel เต็ม), Details (ขยายดู seed/model hash/source ตาม O3-KR6)
  - AI เป็นคนถามนำ (clarifying questions) แทนการบังคับเลือก control ก่อน generate — ต่อยอดจาก O4-KR8
  - **POC non-goal**: ตัด canvas editor แบบ manual drag/resize/reposition (Konva.js/Fabric.js) ออก — แก้ layout ผ่านการพิมพ์บอก AI แล้ว regenerate เฉพาะจุดแทนการลากด้วยมือ (ดู §5)
- **Backend**: FastAPI + Pydantic + PostgreSQL + Redis + Celery/Dramatiq
  - REST API และ real-time update ผ่าน SSE หรือ Redis Pub/Sub
  - Workflow Orchestrator พร้อม state machine, retry, timeout — job state เก็บใน PostgreSQL (ไม่ใช่ in-memory) เพื่อ reconcile ได้หลัง restart/disconnect
- **Auth**: JWT (python-jose/PyJWT) + bcrypt password hashing, ป้องกันทุก endpoint ใต้ `/api/v1/*` ด้วย Bearer token — POC scope: seed user เองผ่าน CLI/script ไม่มีหน้า self-register, role เดียว (ไม่มี RBAC หลาย role จนกว่าจะ scale) — จำเป็นเพราะ backend เข้าถึงได้ผ่าน network แล้ว ไม่ใช่ localhost อย่างเดียว
- **Database**: PostgreSQL ตัวเดียวสำหรับทุกอย่าง — job/workflow state, `User`, และ F2 schemas (`ResearchPack`, `BrandPack`, `DesignBrief`, `DesignSpec`, `QAReport`) — Redis ใช้เป็น broker/pub-sub เท่านั้น ไม่ใช่ source of truth
- **Research**: SearXNG + Playwright + Trafilatura + PyMuPDF + PostgreSQL/pgvector
- **Compositor**: Pango + HarfBuzz + FreeType + Cairo/SVG + libvips/pyvips
- **QA**: PaddleOCR + QR validation + logo validation + layout validation + fact validation

**Compute Plane — DGX Spark** (เข้าถึงจาก control plane ผ่าน private network/VPN — แนะนำ Tailscale/WireGuard, auth ด้วย API key หรือ mTLS)
- **Compute Gateway**: FastAPI service บน DGX ที่ถือ GPU semaphore (concurrency = 1) และ model lifecycle (load/unload กันชนกันระหว่าง 3 โมเดล) รับ job จาก local backend แล้ว callback กลับผ่าน webhook เมื่อเสร็จ แทนการ long-poll ข้าม network
- **Image Generation**: ComfyUI + Qwen-Image-2512
- **Image Editing**: ComfyUI + Qwen-Image-Edit (multi-image reference input) — รองรับ element swap ระหว่างภาพสำหรับโหมด `image_edit`
- **AI Planning**: Ollama/vLLM + Qwen3-30B-A3B-Instruct — เรียกตรงจาก local backend ผ่าน OpenAI-compatible endpoint ไม่ต้องผ่าน Compute Gateway

### F2 — Data Models / Schemas
- `User` (auth: id, email/username, hashed password, role)
- `ResearchPack`
- `BrandPack`
- `DesignBrief`
- `DesignSpec`
- `QAReport`

### F3 — Automated Brand Discovery & Asset Registry

> **POC scope note (revised 2026-07-22, see ADR-001)**: cache-first on-demand Web Discovery เป็น primary runtime flow ตั้งแต่ POC แล้ว ไม่ใช่ hardcode อีกต่อไป — registry/cache lookup → resolve official domain ผ่าน local SearXNG → static HTML/JSON-LD/SVG/CSS extraction → scoring/validation → versioned PostgreSQL/object-storage cache → ใช้งานอัตโนมัติโดยไม่รอ pre-generation human confirmation (score ≥ 80 auto-use) UTCC Brand Pack ที่วางมือยังอยู่ แต่เปลี่ยนบทบาทเป็น deterministic test fixture และ offline fallback เท่านั้น เมื่อ discovery pipeline unreachable

Brand Asset Registry คือ source of truth ที่ระบบใช้งานจริง ไม่ใช่ผลลัพธ์จาก scraping โดยตรง

**Flow หลัก:**

```
User prompt: “ทำโปสเตอร์ UTCC”
              ↓
      Entity Resolver (UTCC = มหาวิทยาลัยหอการค้าไทย)
              ↓
      Brand Registry Lookup
              ↓
    ┌──── มี Brand Pack ────┐
    │                        │
    │ ใช้ข้อมูลที่ approve   │
    │ ตรวจ freshness เบา ๆ   │
    └────────────┬───────────┘
                 │
    ไม่มี / ข้อมูลหมดอายุ
                 ↓
    Official Website Crawler
                 ↓
    Candidate Extractor
                 ↓
    Verification + Confidence Scoring
                 ↓
    Provisional Brand Pack
                 ↓
    Human Review ครั้งแรก
                 ↓
    Verified Brand Registry
                 ↓
         Poster Generation
```

**Components:**

- **F3.1 Entity resolution** — ระบุองค์กรและ official domains
- **F3.2 Official web crawler** — อ่าน HTML, CSS, JSON-LD, SVG, manifest, PDF
- **F3.3 Candidate extraction** — ดึง logo, colors, fonts, URLs, social accounts
- **F3.4 Asset verification + scoring** — ให้คะแนนตาม source, position, format, reuse, consistency
- **F3.5 Brand review UI** — คน approve เฉพาะข้อมูลที่กำกวมหรือ provisional
- **F3.6 Versioned registry** — เก็บ verified Brand Pack พร้อม hash และ history
- **F3.7 Freshness monitor** — ตรวจ source เปลี่ยนแปลงและแจ้งให้ reverify

**Registry content:**

- Organization identity
- Verified domains
- Logo files และ variants
- Brand colors
- Approved fonts
- Clear-space rules
- Official URLs / social accounts
- Source snapshots
- Verification history

**การ extract ตามประเภทข้อมูล:**

| ข้อมูล | แหล่งหลัก | ความน่าเชื่อถือที่คาด | ต้อง human review |
|---|---|---|---|
| ชื่อองค์กร | JSON-LD Organization, About/Contact | 90–98% | ไม่จำเป็น |
| Official domain | JSON-LD, canonical URL, redirect chain | 90–98% | ไม่จำเป็น |
| Official URLs / social | `sameAs`, footer, contact page | 90–98% | เบา |
| Logo candidate | JSON-LD `Organization.logo`, brand guideline, header SVG | 80–95% | ครั้งแรก |
| Logo variant ที่เหมาะ | consistency ข้ามหน้า, aspect ratio | 70–90% | QA เพิ่ม |
| Brand colors | brand guideline, logo SVG, CSS variables | 70–90% | เบา |
| Web fonts | CSS `font-family` | 80–95% | ไม่ใช่ approved font |
| Approved design fonts | brand guideline / design manual | 40–70% | จำเป็น |
| Clear-space rules | brand guideline PDF, identity manual | 20–50% | ไม่ auto-claim |
| Trademark usage | เอกสารทางกฎหมาย | ต่ำ | ระบบตัดสินไม่ได้ |

**Logo candidate scoring ตัวอย่าง:**

| เงื่อนไข | คะแนน |
|---|---|
| อยู่ใน official brand guideline | +40 |
| มาจาก `Organization.logo` | +30 |
| อยู่ใน header หลายหน้า | +20 |
| เป็น SVG | +15 |
| ชื่อไฟล์มี logo/brand/wordmark | +10 |
| มี transparent background | +5 |
| เป็น favicon ขนาดเล็ก | −15 |
| มาจาก og:image | −20 |
| มีคำว่า partner/sponsor | −30 |
| aspect ratio เปลี่ยนระหว่างหน้า | −20 |

- score ≥ 80 → auto-accept candidate
- 60–79 → provisional รอคนตรวจ
- < 60 → ไม่ใช้

**Freshness TTL ที่แนะนำ:**

| ข้อมูล | ตรวจใหม่ |
|---|---|
| Logo / brand guideline | ทุก 30–90 วัน |
| สีและฟอนต์ | ทุก 30–90 วัน |
| Social URLs | ทุก 14–30 วัน |
| Event / admission / promotion | ทุก 1–7 วัน |
| QR destination | ก่อนสร้างทุกครั้ง |
| URL availability | ก่อน export |

### F4 — Templates และ Design System
- 5–8 poster templates
- Typography rules สำหรับภาษาไทยและอังกฤษ
- Font pairing
- Color palette rules
- Layout constraints และ safe zones

### F5 — APIs
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/generations`
- `GET /api/v1/generations/{id}`
- `GET /api/v1/generations/{id}/events`
- `POST /api/v1/generations/{id}/approve`
- `POST /api/v1/generations/{id}/regenerate`
- `POST /api/v1/generations/{id}/repair`
- `POST /api/v1/generations/{id}/export`
- `GET /api/v1/brands`
- `POST /api/v1/brands/resolve`
- `POST /api/v1/brands/discover`
- `GET /api/v1/brands/{id}`
- `POST /api/v1/brands/{id}/verify`
- `POST /api/v1/brands/{id}/approve`
- `GET /api/v1/brands/{id}/candidates`
- `GET /api/v1/brands/{id}/history`
- `GET/POST /api/v1/assets/*`
- `GET /api/v1/research/{id}`

> ทุก endpoint ยกเว้น `/auth/login` ต้องมี `Authorization: Bearer <token>` — enforce ที่ FastAPI dependency ชั้นเดียว ไม่ต้องทำ per-route

### F6 — Documentation
- Software Requirements Specification
- System Architecture Document
- Database schema และ Pydantic schemas
- Template definitions
- Prompt templates
- Test specification
- Deployment guide
- Operation and maintenance guide

### F7 — Test Sets และ Benchmarks
- 100 general image prompts
- 100 poster prompts
- 50 infographic prompts
- 500 Thai text strings
- 20 known brands, 20 unknown brands
- 20 expired/outdated data scenarios
- 20 incorrect-logo traps
- 20 QR tests
- 20 network failure tests

---

## 4. Operating Modes (ฟีเจอร์หลัก)

| Mode | รายละเอียด |
|---|---|
| `general_image` | สร้างคน สัตว์ บ้าน สินค้า ฉาก หรือภาพทั่วไป ไม่ผ่าน design compositor เต็มระบบ |
| `poster` | สร้างงานที่มี hero image, headline, supporting copy, CTA, logo, QR, contact/footer |
| `infographic` | สร้างงานที่มี verified facts, stat cards, timeline, comparison, icons, deterministic charts, sources |
| `image_edit` | รับภาพอ้างอิง 2 ภาพ + text instruction เพื่อ swap/แก้องค์ประกอบระหว่างภาพ ผ่าน Qwen-Image-Edit (multi-image input) — ข้อความในภาพที่ถูกแก้ต้องผ่าน QA (OCR) เดียวกับ mode อื่นก่อนถือว่าใช้งานได้จริง โดยเฉพาะภาษาไทยซึ่งยังไม่ผ่านการ validate เท่า base model |

---

## 5. Non-Goals / Out-of-Scope

- ไม่ฝึก foundation image model ใหม่ตั้งแต่ต้น
- ไม่สร้าง AR image model หรือ VQ-VAE ใหม่
- ไม่ให้ image model วาดโลโก้ ข้อความ หรือ QR
- ไม่เชื่อข้อความที่ `image_edit` แก้ในภาพโดยไม่ผ่าน QA (OCR) เดียวกับ pipeline หลักก่อน โดยเฉพาะภาษาไทย
- ไม่ตัดสินสิทธิ์เครื่องหมายการค้าอัตโนมัติ 100%
- ไม่รองรับผู้ใช้พร้อมกันจำนวนมากใน POC/MVP (เป้าหมายคือตัวเองหรือกลุ่มเล็ก ไม่ใช่ 20,000 คน)
- ไม่ทำ slide deck หลายสิบหน้า
- ไม่ปล่อยผลงานไป social media โดยไม่ review
- ไม่ทำ canvas editor แบบ manual drag/resize/reposition (Konva.js/Fabric.js) ใน POC — แก้ layout ผ่าน regenerate-with-feedback ในแชทแทน

---

## 6. Success Criteria สำหรับ MVP

| Metric | Target |
|---|---|
| Exact final text | 100% |
| QR decode success | 100% |
| Verified logo integrity | 100% |
| Text overflow | 0 |
| Unsupported factual claims | 0 |
| Job recovery after retryable failure | ≥ 95% |
| Human design rating | ≥ 4/5 |
| Poster accepted without major edit | ≥ 75% |
| Known-brand publishable output | ≥ 85% |

---

## 7. Key Risks

| Risk | Mitigation |
|---|---|
| OOM จากการโหลดหลายโมเดลพร้อมกัน | GPU queue + model unload/load lifecycle |
| ข้อความไทยผิดเพี้ยนใน diffusion | ใช้ deterministic compositor ด้วย Pango/HarfBuzz |
| Fake logo หรือ fake text | Verified asset registry + mask logo zone + logo QA |
| ข้อมูลล้าหลังหรือผิด | Official sources only + confidence threshold + expiry check |
| Model tag เปลี่ยน | Pin exact model digest ห้ามใช้ latest |
| Scrape ได้ logo/สี/ฟอนต์ผิดจาก campaign หรือ partner | Candidate scoring + human review + versioned registry |
| Source เปลี่ยนแล้ว asset เก่าถูก overwrite | TTL + content hash diff + `review_required` state |
| robots.txt หรือ rate limit ของเว็บเป้าหมาย | เคารพ Robots Exclusion Protocol + rate limit + user agent |
| Web fonts ถูกเข้าใจผิดว่าเป็น approved fonts | แยก `web_fonts_detected` กับ `approved_design_fonts` |
| AI Planning infer Mode/Template/Research depth/Palette ผิด แล้ว generate ไปเลยโดยไม่ถาม | AI ต้องพูดสรุปสิ่งที่เข้าใจกลับมาในแชทก่อน generate ทุกครั้ง (confirm-before-generate) ไม่ใช่ infer เงียบๆ — ผู้ใช้แก้ได้ทันทีในแชทก่อนเริ่มงานจริง |
| Local PC (control plane) offline ระหว่าง sleep/reboot/network drop ขณะ DGX ยังทำงานปกติ | Job state ทั้งหมดเก็บใน PostgreSQL, ใช้ job UUID reconcile กับ Compute Gateway หลัง restart, ไม่พึ่ง in-memory state |
| Qwen-Image, Qwen-Image-Edit, และ Qwen3-30B แข่งกันใน unified memory เดียวกันบน DGX (3 โมเดลแทนที่จะเป็น 2) | วัด memory footprint จริงตั้งแต่ POC, ขยาย GPU queue ให้ sequencing รองรับ 3 โมเดล ไม่ใช่แค่ image + LLM |
| ข้อความภาษาไทยที่ `image_edit` แก้ผิดเพี้ยน เพราะ text-editing ของ Qwen-Image-Edit ยัง validate หลักๆ กับอังกฤษ/จีน | ผ่าน OCR QA เดียวกับ pipeline หลักก่อนใช้งานจริง ไม่ auto-trust ผลจาก edit model |

---

## 8. First Milestone (งานแรกที่ควรเริ่ม)

**Phase 0 — Feasibility Study**: 2–4 สัปดาห์

Vertical slice แรกจาก prompt:
> “ทำโปสเตอร์โปรโมต UTCC สำหรับนักเรียน ม.ปลาย”

1. สร้าง UTCC Brand Pack แบบ verified
2. สร้าง ResearchPack
3. สร้าง DesignSpec
4. Generate hero image ด้วย Qwen-Image
5. Render Thai text ด้วย Pango/HarfBuzz
6. วาง official logo
7. สร้าง QR
8. Compose final poster
9. OCR + QR + logo QA
10. แสดงใน review UI
11. ทดสอบ round trip Local PC (control plane) ↔ DGX Spark (compute plane) ผ่าน Compute Gateway — รวม webhook callback และ job state reconciliation หลัง restart
12. ทดสอบโหมด `image_edit` กับภาพอ้างอิง 2–3 คู่ (element swap) ผ่าน Qwen-Image-Edit พร้อม OCR QA บนข้อความที่ถูกแก้

---

## 9. Timeline

### 9.1 POC Timeline (ปัจจุบัน — เป้าหมาย 2 เดือน / 8 สัปดาห์, 1 คน + AI-assisted coding)

ตัดออกจากแผนเดิมทั้งหมด: F3 brand automation (ใช้ hardcoded Brand Pack แทน), F6 formal docs (SRS/architecture doc เต็มรูปแบบ), F7 benchmark เต็มขนาด (100+100+50 prompts → เหลือ ~10–20 พอตรวจสอบได้), Konva/Fabric.js manual canvas editing, concurrent-user hardening

| สัปดาห์ | งาน |
|---|---|
| 1 | Phase 0 vertical slice (§8, ข้อ 1–10) — UTCC Brand Pack แบบ hardcode, prompt เดียวจบ end-to-end |
| 2 | Compute Gateway บน DGX (GPU semaphore, model lifecycle, webhook callback) + spike test โหลด Qwen-Image / Qwen-Image-Edit / Qwen3-30B พร้อมกันเพื่อวัด memory footprint จริงตั้งแต่ต้น ไม่รอจนสัปดาห์หลัง |
| 3 | โหมด `poster` เต็มรูปแบบ — 3–5 templates (ลดจาก 5–8), typography rules ไทย/อังกฤษ, candidate 2 ต่อ prompt |
| 4 | โหมด `infographic` — stat cards + deterministic chart, ข้อมูล hardcode (เลื่อน fact-verification/sourcing ไปหลัง POC) |
| 5 | โหมด `image_edit` — Qwen-Image-Edit multi-image swap + OCR QA บนข้อความที่ถูกแก้ |
| 6 | Frontend ขั้นต่ำที่ใช้งานได้จริง — prompt input, job progress (SSE), candidate gallery, review/approve, export (PNG/JPEG/JSON) |
| 7 | Internal testing กับกลุ่มเล็ก, แก้ bug จากการใช้งานจริง |
| 8 | Buffer + polish + เอกสารเท่าที่จำเป็น (README/deployment note ไม่ใช่ SRS เต็มรูปแบบ) |

**จุดเสี่ยงที่สุด**: สัปดาห์ 2 (Compute Gateway + memory spike) และสัปดาห์ 5 (`image_edit` ความแม่นยำข้อความไทย) — ถ้าสัปดาห์ 2 เจอ OOM หรือ `image_edit` ใช้ไม่ได้จริงในสัปดาห์ 5 ต้องตัดสินใจเร็วว่าจะ scope down หรือขยับ buffer มาใช้ตรงนั้นแทน

### 9.2 Production Roadmap (หลัง POC ผ่านและตัดสินใจ scale — ไม่ใช่ commitment ตอนนี้)

| Phase | ระยะเวลา |
|---|---|
| Phase 0 — Feasibility Study | 2–4 สัปดาห์ |
| Phase 1 — Requirement Analysis | 1–2 สัปดาห์ |
| Phase 2 — System Architecture Design | 2–3 สัปดาห์ |
| Phase 3 — Detailed Design | 3–4 สัปดาห์ |
| Phase 4 — Implementation | 8–12 สัปดาห์ |
| Phase 5 — Integration and System Testing | 4–6 สัปดาห์ |
| Phase 6 — User Acceptance Testing | 2–4 สัปดาห์ |
| Phase 7 — Deployment | 1–2 สัปดาห์ |
| **รวม** | **5–8 เดือน** |

---

## 10. Changelog

### 2026-07-22 — Cache-first Brand Discovery replaces hardcoded pack as primary flow (ADR-001)
- F3 Automated Brand Discovery & Asset Registry เลื่อนขึ้นมาเป็น POC primary runtime flow แทน hardcoded UTCC pack — §F3
- Flow: registry/cache lookup → official-domain resolution ผ่าน local SearXNG → static HTML/JSON-LD/SVG/CSS extraction → candidate scoring/validation → versioned PostgreSQL/object-storage cache → automatic use โดยไม่รอ pre-generation confirmation (score ≥ 80 auto-use ตาม §7.3 ของ PROD.md)
- Caching policy: stale-while-revalidate สำหรับ asset ที่นิ่ง (logo/color/font), TTL สั้นกว่าสำหรับข้อมูลที่เปลี่ยนบ่อย (event/ราคา/วันที่), ตรวจ QR destination ใหม่ทุกครั้งก่อน export
- Cached asset version ห้าม overwrite ของเดิม — เปลี่ยนแล้วสร้าง version ใหม่ + mark `review_required`
- ห้าม image model วาด official logo ที่ยังไม่ผ่าน confident verification (score < 60 หรือไม่มี cache) — ไม่มี logo ที่ verify ไม่ได้จะไม่ใส่ logo เลย ไม่ generate ประมาณเอา
- UTCC Brand Pack วางมือเดิมยังอยู่แต่เปลี่ยนบทบาทเป็น deterministic test fixture + offline fallback เท่านั้น ไม่ใช่ primary path แล้ว
- ดู `docs/adr/0001-brand-discovery-cache-first.md` สำหรับ rationale เต็ม และ PROD.md §7.1/§1.4 สำหรับ normative spec ที่แก้ตาม

### 2026-07-22 — Full chatbot shell (supersedes dashboard/panel layout below)
- Frontend เปลี่ยนจาก dashboard-style (New Project/Dashboard/Create/Brand Registry/History nav + Properties/Layers/Export side panel) เป็น chatbot shell เต็มรูปแบบ — sidebar ซ้าย: New Chat + ประวัติแชท ~10 รายการ + Settings/Logout, ไม่มี sidebar ขวา — §F1
- แทนที่ "Advanced controls panel" ด้วย confirm-before-generate: AI พูดสรุปสิ่งที่เข้าใจกลับมาในแชทก่อน generate แทนการโชว์ panel — §O4-KR8, §7
- ตัด manual canvas editing (drag/resize/reposition) ออกจาก POC ทั้งหมด ใช้ regenerate-with-feedback ผ่านแชทแทน — §O4, §5

### 2026-07-22 — Chat-first hybrid Create page
- Create page ใช้ chat box เป็น input หลัก (แบบ ChatGPT), ไม่บังคับเลือก Mode/Template/Research depth/Palette ก่อนเริ่ม — ให้ AI Planning infer แล้วโชว์เป็น inline summary chip ที่ override ได้ผ่าน Advanced controls panel (side, collapsed by default) — §F1, §O4-KR8, §7

### 2026-07-22 — Auth + explicit Database
- เพิ่ม Auth (JWT + bcrypt) เป็น component แยกใน F1 — protect ทุก endpoint ยกเว้น login, POC scope: seed user เอง ไม่มี self-register/RBAC
- แยก Database (PostgreSQL) เป็น component ของตัวเองใน F1 แทนที่จะฝังอยู่ใต้ Backend เฉยๆ ระบุชัดว่าเก็บอะไรบ้าง
- เพิ่ม `User` schema ใน F2, เพิ่ม `/auth/login`, `/auth/me` ใน F5

### 2026-07-22 — 2-month POC replan
- แทนที่ §9 ด้วยแผน 8 สัปดาห์ (§9.1) โดยตัด F3 automation, F6 formal docs, F7 full benchmark, canvas editing ออกจากขอบเขต POC — เดิม §9 (5–8 เดือน, ทีม 3 คน) เลื่อนเป็น production roadmap ใน §9.2
- ปรับ user เป้าหมายจาก 20,000 คนทั้งมหาวิทยาลัย เป็นตัวเองหรือกลุ่มเล็กสำหรับช่วง POC — §header, §5
- ระบุจุดเสี่ยงที่ต้องทดสอบเร็ว (Compute Gateway memory spike, `image_edit` ความแม่นยำข้อความไทย) แทนที่จะรอให้เจอตอนท้ายแผน

### 2026-07-22 — Deployment split + image_edit capability
- เพิ่ม Control Plane (local PC) / Compute Plane (DGX Spark) split — §O3, §F1
- เพิ่ม Compute Gateway เป็น service กลางบน DGX สำหรับ GPU queue, model lifecycle, webhook callback
- เพิ่มโหมด `image_edit` (reference-based swap ผ่าน Qwen-Image-Edit) — §O1-KR8, §4, §5
- เพิ่ม risk เรื่อง local PC availability, 3-model memory contention, และความแม่นยำข้อความไทยจาก edit model — §7
- ทำเครื่องหมาย F3 (Brand Discovery & Asset Registry) เป็นเป้าหมาย production ไม่ใช่ POC scope
- เพิ่มขั้นตอน validate deployment split และ `image_edit` ใน Phase 0 milestone — §8

---

*สร้างเมื่อ: 2026-07-22*
