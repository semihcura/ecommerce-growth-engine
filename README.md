# 🚀 E-Commerce Growth & Retention Engine: Margin Guardrail Cockpit

An enterprise-grade customer retention and automated campaign engine combining statistical RFM segmentation, financial margin guardrails, and fault-tolerant LLM personalization.

Built with **Python**, **Pandas**, **Streamlit**, and **Google Gemini 2.5 Flash**.

---

## 📌 Executive Summary & Business Problem

Traditional e-commerce discount campaigns suffer from two major structural flaws:
1. **Margin Erosion (Marj Erimesi):** Distributing blanket percentage discounts to loyal/high-value customers who would purchase regardless, destroying net margins.
2. **Generic Re-engagement:** Static push notifications fail to recover churn-risk customers due to lack of personalized, dynamic cart-level context.

This project implements a **Margin Guardrail Cockpit** that enforces strict financial policy constraints before triggering AI-driven retention notifications, paired with an offline fallback mechanism ensuring 99.99% system uptime.

---

## 🛠️ Architecture & Core Engine

```text
[ Kaggle Online Retail II ] 
            │
            ▼
[ ETL & Statistical RFM Pipeline (qcut 1-5) ]
            │
            ▼
[ Margin Guardrail Policy Engine ]
   ├── VIP Segments (Champions/Loyal) ──> 0% Cash Discount (VIP Fast Delivery / Gifts only)
   ├── At-Risk / Churn Segments       ──> Dynamic Recovery Budget Cap (B_max <= Basket * X%)
   └── Default Segments               ──> Baseline Offer Limits
            │
            ▼
[ Fault-Tolerant Personalization Router ]
   ├── Gemini 2.5 Flash API (Structured JSON Schema)
   └── Zero-Downtime Fallback Rule Engine (Auto-switches on 429 Rate Limit / Timeout)
            │
            ▼
[ Streamlit Dark-SaaS Executive Cockpit & Push Mockup ]
```

---

## 📊 Key Highlights

* **Statistical Rigor:** Quantile-based RFM scoring (`pd.qcut`) on real-world transaction logs (500k+ rows) mapping users into 10 behavioral clusters.
* **Financial Guardrails:** Dynamic budget simulation calculating real-time marketing exposure across customer tiers.
* **Deterministic AI Generation:** Enforces strict JSON schemas on Gemini output (`baslik`, `mesaj`, `kupon_kodu`) with strict character limits.
* **High Availability (Resilience):** Simulates API quota exhaustion (HTTP 429 / Timeouts) and gracefully switches to local template engines with dynamic hash codes.

---

## 💻 Quickstart

**1. Clone repository:**
```bash
git clone https://github.com/semihcura/ecommerce-growth-engine.git
cd ecommerce-growth-engine
```

**2. Install dependencies:**
```bash
pip install streamlit pandas plotly requests
```

**3. Configure API Secrets:**
Create `.streamlit/secrets.toml`:
```toml
GEMINI_API_KEY = "your_google_gemini_api_key"
```

**4. Run the Cockpit:**
```bash
streamlit run margin_guardrail_dashboard.py
```
