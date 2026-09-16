"""
Margin Guardrail Cockpit — Streamlit Dashboard
================================================
RFM segmentasyonu + Marj Koruma Motoru + LLM destekli win-back bildirim
önizlemesini tek ekranda birleştiren interaktif kontrol paneli.

Çalıştırma:
    pip install streamlit pandas numpy plotly requests
    streamlit run margin_guardrail_dashboard.py

Veri kaynağı:
    Aynı klasörde "rfm_results_guardrails.csv" veya "rfm_results.csv" varsa
    otomatik yüklenir. Yoksa dashboard, gösterim amaçlı sentetik bir RFM
    veri seti üreterek "kutudan çıktığı gibi" (out-of-the-box) çalışır.

LLM entegrasyonu:
    Sidebar'dan Gemini veya OpenAI seçilebilir. API anahtarı ortam
    değişkeninden (GEMINI_API_KEY / OPENAI_API_KEY) ya da st.secrets'tan
    okunur. Anahtar yoksa, kota/zaman aşımı hatası alınırsa ya da model
    beklenen JSON şemasına uymayan bir çıktı üretirse sistem otomatik ve
    SESSIZCE (kullanıcıya UI üzerinden bildirerek) yerel kural tabanlı
    şablona (fallback) düşer — hiçbir durumda çökmez.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
import streamlit as st

# =========================================================================== #
# 0. SABİTLER / İŞ KURALLARI
# =========================================================================== #

VIP_SEGMENTS = ["champions", "loyal_customers"]
RESCUE_SEGMENTS = ["at_risk", "cant_loose"]

ALL_SEGMENTS = [
    "champions", "loyal_customers", "potential_loyalists", "new_customers",
    "promising", "need_attention", "about_to_sleep", "at_risk",
    "cant_loose", "hibernating",
]

SEGMENT_LABELS_TR = {
    "champions": "Şampiyonlar", "loyal_customers": "Sadık Müşteriler",
    "potential_loyalists": "Potansiyel Sadıklar", "new_customers": "Yeni Müşteriler",
    "promising": "Umut Vadedenler", "need_attention": "İlgi Bekleyenler",
    "about_to_sleep": "Uykuya Geçmek Üzere", "at_risk": "Risk Altında",
    "cant_loose": "Kaybedilmemesi Gerekenler", "hibernating": "Uykuda (Pasif)",
}

DEFAULT_CAPS = {"vip": 10, "rescue": 20, "standard": 10}

DEMO_ABANDONED_PRODUCTS = [
    "15CM CHRISTMAS GLASS BALL", "PINK CHERRY LIGHTS", "RECORD FRAME 7\" SINGLE SIZE",
    "VINTAGE KITCHEN SCALE", "RETRO SPOT TEA SET", "WOODEN PICTURE FRAME",
    "SET OF 3 CAKE TINS", "PARTY BUNTING", "TRAVEL CARD WALLET", "JUMBO BAG RED RETROSPOT",
]

DATA_CANDIDATES = ["rfm_results_guardrails.csv", "rfm_results.csv"]


class QuotaExceededError(Exception):
    """LLM sağlayıcısı kota/oran limiti döndürdüğünde fırlatılır."""


class SchemaValidationError(Exception):
    """LLM çıktısı beklenen JSON şemasına uymadığında fırlatılır."""


# =========================================================================== #
# 1. SAYFA AYARI & DARK SAAS TEMA
# =========================================================================== #

def configure_page() -> None:
    st.set_page_config(
        page_title="Margin Guardrail Cockpit",
        page_icon="🛡️",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def inject_theme_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg-0: #0b0f19;
            --bg-1: #111827;
            --bg-2: #1a2234;
            --border: #263049;
            --text-hi: #e5e9f0;
            --text-lo: #8b95a7;
            --accent: #6366f1;
            --accent-2: #22d3ee;
            --good: #22c55e;
            --warn: #f59e0b;
            --danger: #ef4444;
        }
        html, body, [class*="css"]  { color: var(--text-hi); }
        .stApp { background: radial-gradient(circle at 20% -10%, #1b2340 0%, var(--bg-0) 45%) fixed; }
        section[data-testid="stSidebar"] {
            background: var(--bg-1); border-right: 1px solid var(--border);
        }
        h1, h2, h3 { color: var(--text-hi) !important; letter-spacing: -0.02em; }
        p, span, label, div { color: var(--text-hi); }

        .kpi-card {
            background: linear-gradient(160deg, var(--bg-2) 0%, var(--bg-1) 100%);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 18px 20px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.35);
        }
        .kpi-label {
            font-size: 12.5px; text-transform: uppercase; letter-spacing: 0.08em;
            color: var(--text-lo); margin-bottom: 6px; font-weight: 600;
        }
        .kpi-value { font-size: 28px; font-weight: 700; color: var(--text-hi); }
        .kpi-sub { font-size: 12.5px; color: var(--accent-2); margin-top: 4px; }

        .section-card {
            background: var(--bg-1); border: 1px solid var(--border);
            border-radius: 16px; padding: 20px 22px; margin-bottom: 18px;
        }

        .badge {
            display: inline-block; padding: 3px 10px; border-radius: 999px;
            font-size: 11.5px; font-weight: 700; letter-spacing: 0.03em;
        }
        .badge-vip { background:#6366f122; color:#a5b4fc; border:1px solid #6366f155; }
        .badge-rescue { background:#f5980922; color:#fbbf24; border:1px solid #f5980955; }
        .badge-standard { background:#22d3ee22; color:#67e8f9; border:1px solid #22d3ee55; }

        /* --- Telefon kilit ekranı mockup --- */
        .phone-frame {
            width: 300px; margin: 0 auto; padding: 26px 16px 34px;
            background: linear-gradient(180deg, #0c1220 0%, #05070c 100%);
            border-radius: 42px; border: 6px solid #050810;
            box-shadow: 0 20px 60px rgba(0,0,0,0.55), inset 0 0 0 1px #1c2438;
            position: relative;
            background-image:
                radial-gradient(circle at 50% 8%, rgba(255,255,255,0.03), transparent 60%),
                url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="300" height="560"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%25" stop-color="%23141c30"/><stop offset="100%25" stop-color="%23070a12"/></linearGradient></defs><rect width="300" height="560" fill="url(%23g)"/></svg>');
        }
        .phone-notch {
            width: 120px; height: 22px; background: #05070c; border-radius: 0 0 16px 16px;
            margin: -26px auto 18px; box-shadow: inset 0 -2px 4px rgba(255,255,255,0.03);
        }
        .phone-time { text-align:center; font-size: 46px; font-weight: 300; color: #f2f4f8; margin-top: 6px;}
        .phone-date { text-align:center; font-size: 13px; color: #9aa4bd; margin-bottom: 22px; }
        .notification-card {
            background: rgba(255,255,255,0.09);
            backdrop-filter: blur(6px);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 18px; padding: 14px 16px; margin: 0 4px 10px;
        }
        .notif-header { display:flex; align-items:center; gap:8px; margin-bottom:6px; }
        .app-icon {
            width:22px; height:22px; border-radius:6px; background:var(--accent);
            display:flex; align-items:center; justify-content:center; font-size:13px;
        }
        .app-name { font-size: 12.5px; color:#c7cfe0; font-weight:600; }
        .notif-time { color:#7c869c; font-weight: 400; margin-left: 6px; }
        .notif-title { font-size: 14.5px; font-weight: 700; color:#f5f7fb; margin-bottom: 3px; }
        .notif-body { font-size: 13.2px; color:#d6dbe8; line-height:1.35; }
        .notif-coupon {
            display:inline-block; margin-top:9px; padding: 4px 10px; border-radius:8px;
            background: linear-gradient(90deg, #6366f1, #22d3ee); color:#0b0f19;
            font-weight:800; font-size: 12.5px; letter-spacing: 0.06em;
        }
        .source-badge {
            display:block; text-align:center; margin-top: 14px; padding: 5px 0;
            border-radius: 999px; font-size: 11px; font-weight:700; letter-spacing:0.04em;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# =========================================================================== #
# 2. VERİ KATMANI
# =========================================================================== #

@st.cache_data(show_spinner=False)
def load_base_data() -> pd.DataFrame:
    """Önceki katmanların ürettiği CSV varsa onu yükler; yoksa demo amaçlı
    sentetik ama istatistiksel olarak makul bir RFM veri seti üretir."""
    for candidate in DATA_CANDIDATES:
        p = Path(candidate)
        if p.exists():
            df = pd.read_csv(p)
            df = _ensure_required_columns(df)
            return df
    return _generate_synthetic_demo_data()


def _ensure_required_columns(df: pd.DataFrame) -> pd.DataFrame:
    required = {"Segment", "Recency", "Frequency", "Monetary"}
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"Girdi CSV'sinde eksik kolonlar var: {missing}")
    if "Customer ID" not in df.columns:
        df["Customer ID"] = np.arange(1, len(df) + 1)
    if "ortalama_sepet_tl" not in df.columns:
        df["ortalama_sepet_tl"] = (df["Monetary"] / df["Frequency"].replace(0, np.nan)).fillna(0).round(2)
    return df


def _generate_synthetic_demo_data(n: int = 450, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    weights = [0.14, 0.20, 0.12, 0.05, 0.02, 0.05, 0.07, 0.13, 0.02, 0.20]
    segments = rng.choice(ALL_SEGMENTS, size=n, p=weights)

    recency, frequency, monetary = [], [], []
    for seg in segments:
        if seg in ("champions", "loyal_customers", "cant_loose"):
            recency.append(rng.integers(1, 60))
            frequency.append(rng.integers(6, 25))
            monetary.append(round(rng.uniform(2000, 15000), 2))
        elif seg in ("at_risk", "hibernating", "about_to_sleep"):
            recency.append(rng.integers(150, 500))
            frequency.append(rng.integers(1, 5))
            monetary.append(round(rng.uniform(200, 2000), 2))
        else:
            recency.append(rng.integers(20, 150))
            frequency.append(rng.integers(1, 8))
            monetary.append(round(rng.uniform(300, 4000), 2))

    df = pd.DataFrame({
        "Customer ID": np.arange(10000, 10000 + n),
        "Segment": segments,
        "Recency": recency,
        "Frequency": frequency,
        "Monetary": monetary,
    })
    df["ortalama_sepet_tl"] = (df["Monetary"] / df["Frequency"]).round(2)
    return df


def recompute_budgets(df: pd.DataFrame, caps_pct: dict) -> pd.DataFrame:
    """Sidebar'daki slider değerlerine göre bütçe tavanlarını YENİDEN hesaplar.
    Tamamen vektörizedir; her slider hareketinde anında tekrar çalışır."""
    out = df.copy()

    is_vip = out["Segment"].isin(VIP_SEGMENTS)
    is_rescue = out["Segment"].isin(RESCUE_SEGMENTS)

    cap_fraction = np.select(
        [is_vip, is_rescue],
        [caps_pct["vip"] / 100.0, caps_pct["rescue"] / 100.0],
        default=caps_pct["standard"] / 100.0,
    )
    out["uygulanan_tavan_%"] = cap_fraction * 100
    out["maksimum_butce_tl"] = (out["ortalama_sepet_tl"] * cap_fraction).round(2)
    out["tesvik_tipi"] = np.select(
        [is_vip, is_rescue],
        ["VIP Hediye / Hızlı Teslimat", "Kurtarma İndirimi / Ücretsiz Kargo"],
        default="Standart Teşvik Kuponu",
    )
    out["nakit_indirim_yasak"] = is_vip
    return out


# =========================================================================== #
# 3. SIDEBAR — SİMÜLASYON KONTROLLERİ
# =========================================================================== #

def render_sidebar() -> tuple[dict, str, bool]:
    st.sidebar.markdown("## 🛡️ Guardrail Kontrolleri")
    st.sidebar.caption("Slider'ları hareket ettirdikçe tüm tablo ve KPI'lar anında yeniden hesaplanır.")

    st.sidebar.markdown("#### Bütçe Tavanı Simülasyonu")
    vip_cap = st.sidebar.slider(
        "🏆 Champions / Loyal — tavan (%)", min_value=0, max_value=30,
        value=DEFAULT_CAPS["vip"], step=1,
        help="Bu segmentlere nakit/yüzde indirim YASAK; tavan sadece hediye/hızlı teslimat bütçesini sınırlar.",
    )
    rescue_cap = st.sidebar.slider(
        "🚨 At-Risk / Cant-Loose — tavan (%)", min_value=0, max_value=50,
        value=DEFAULT_CAPS["rescue"], step=1,
        help="Terk riski yüksek segmentler için kurtarma indirimi / ücretsiz kargo tavanı.",
    )
    standard_cap = st.sidebar.slider(
        "📦 Diğer Segmentler — tavan (%)", min_value=0, max_value=30,
        value=DEFAULT_CAPS["standard"], step=1,
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("#### LLM Bildirim Motoru")
    provider = st.sidebar.selectbox("Sağlayıcı", ["gemini", "openai"], index=0)
    force_fallback = st.sidebar.toggle(
        "🔧 Kota Aşımını Simüle Et (Fallback'i zorla test et)", value=False,
        help="Açarsanız gerçek API'ye gitmeden doğrudan yerel kural şablonunu tetikler.",
    )
    key_env = "GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"
    has_key = bool(_get_api_key(key_env))
    if not has_key:
        st.sidebar.caption(f"ℹ️ `{key_env}` tanımlı değil — API çağrısı otomatik olarak fallback'e düşecek.")

    caps = {"vip": vip_cap, "rescue": rescue_cap, "standard": standard_cap}
    return caps, provider, force_fallback


# =========================================================================== #
# 4. KPI KARTLARI & GRAFİKLER
# =========================================================================== #

def render_kpi_row(df: pd.DataFrame) -> None:
    total_customers = len(df)
    total_revenue = df["Monetary"].sum()
    total_budget = df["maksimum_butce_tl"].sum()
    budget_ratio = (total_budget / total_revenue * 100) if total_revenue else 0
    vip_share = df.loc[df["Segment"].isin(VIP_SEGMENTS), "Monetary"].sum() / total_revenue * 100 if total_revenue else 0

    cols = st.columns(4)
    kpis = [
        ("TOPLAM MÜŞTERİ PORTFÖYÜ", f"{total_customers:,}", "aktif RFM kaydı"),
        ("TOPLAM CİRO (₺)", f"{total_revenue:,.0f}", "portföy toplamı"),
        ("TOPLAM GUARDRAIL BÜTÇESİ (₺)", f"{total_budget:,.0f}", f"cironun %{budget_ratio:.1f}'i"),
        ("CHAMPIONS+LOYAL CİRO PAYI", f"%{vip_share:.1f}", "en kârlı segment ağırlığı"),
    ]
    for col, (label, value, sub) in zip(cols, kpis):
        col.markdown(
            f"""<div class="kpi-card">
                    <div class="kpi-label">{label}</div>
                    <div class="kpi-value">{value}</div>
                    <div class="kpi-sub">{sub}</div>
                </div>""",
            unsafe_allow_html=True,
        )


def render_segment_charts(df: pd.DataFrame) -> None:
    seg_summary = (
        df.groupby("Segment")
        .agg(Musteri=("Segment", "count"), Ciro=("Monetary", "sum"), Butce=("maksimum_butce_tl", "sum"))
        .reset_index()
        .sort_values("Ciro", ascending=False)
    )
    seg_summary["Segment_TR"] = seg_summary["Segment"].map(SEGMENT_LABELS_TR).fillna(seg_summary["Segment"])

    c1, c2 = st.columns([1.3, 1])

    with c1:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("##### Segment Bazlı Ciro Dağılımı")
        fig = px.bar(
            seg_summary, x="Segment_TR", y="Ciro", color="Ciro",
            color_continuous_scale=["#1e293b", "#6366f1", "#22d3ee"],
        )
        fig.update_layout(
            template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            height=340, margin=dict(l=10, r=10, t=10, b=10),
            xaxis_title=None, yaxis_title="Ciro (₺)", coloraxis_showscale=False,
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("##### Müşteri Sayısı Payı")
        fig2 = go.Figure(data=[go.Pie(
            labels=seg_summary["Segment_TR"], values=seg_summary["Musteri"], hole=0.55,
            marker=dict(colors=px.colors.sequential.Plasma_r),
        )])
        fig2.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
            height=340, margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(font=dict(size=10)),
        )
        st.plotly_chart(fig2, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)


def render_budget_table(df: pd.DataFrame) -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("##### Segment Bazlı Bütçe Tavanı Tablosu (Slider'lara Göre Canlı)")
    table = (
        df.groupby("Segment")
        .agg(
            Musteri_Sayisi=("Segment", "count"),
            Ort_Sepet_TL=("ortalama_sepet_tl", "mean"),
            Uygulanan_Tavan_Pct=("uygulanan_tavan_%", "first"),
            Ort_Butce_TL=("maksimum_butce_tl", "mean"),
            Toplam_Butce_TL=("maksimum_butce_tl", "sum"),
        )
        .round(2)
        .sort_values("Toplam_Butce_TL", ascending=False)
    )
    st.dataframe(table, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================================== #
# 5. LLM PROMPT ŞEMASI
# =========================================================================== #

def build_llm_prompt_payload(customer: pd.Series, abandoned_product: str) -> dict:
    """LLM'e gönderilecek KISITLI (constrained) JSON prompt şeması.
    Model SADECE 'cikti_semasi' alanına uyan bir JSON döndürmekle yükümlü;
    bütçe ve indirim kısıtları burada sabitlenir, model bunları DEĞİŞTİREMEZ."""
    is_vip = customer["Segment"] in VIP_SEGMENTS
    return {
        "gorev": "musteri_winback_bildirimi_olustur",
        "kisitlar": {
            "para_birimi": "TRY",
            "maksimum_butce_tl": float(customer["maksimum_butce_tl"]),
            "nakit_veya_yuzde_indirim_yasak": bool(is_vip),
            "ton": "sicak_ve_kisisel" if is_vip else "aciliyet_hissettiren",
        },
        "musteri_baglami": {
            "musteri_id": str(customer["Customer ID"]),
            "segment": customer["Segment"],
            "terk_edilen_urun": abandoned_product,
            "onerilen_tesvik_tipi": customer["tesvik_tipi"],
            "son_islemden_bu_yana_gun": int(customer["Recency"]),
        },
        "cikti_semasi": {
            "tip": "object",
            "zorunlu_alanlar": ["baslik", "mesaj", "kupon_kodu"],
            "alanlar": {
                "baslik": {"tip": "string", "max_karakter": 40},
                "mesaj": {"tip": "string", "max_karakter": 120},
                "kupon_kodu": {"tip": "string", "format": "XXXX-XXXX"},
            },
        },
        "talimat": (
            "SADECE cikti_semasina uyan geçerli bir JSON nesnesi döndür. "
            "Açıklama, markdown, kod bloğu EKLEME. nakit_veya_yuzde_indirim_yasak=true ise "
            "mesajda asla yüzde veya TL indirimi telaffuz etme, sadece hediye/hızlı teslimat vurgula."
        ),
    }


def _validate_notification_schema(data: dict) -> None:
    required = {"baslik", "mesaj", "kupon_kodu"}
    if not isinstance(data, dict) or not required.issubset(data.keys()):
        raise SchemaValidationError(f"Beklenen alanlar eksik: {required - set(data.keys())}")
    if len(str(data["baslik"])) > 60 or len(str(data["mesaj"])) > 200:
        raise SchemaValidationError("Alan uzunlukları şema limitlerini aşıyor.")


# =========================================================================== #
# 6. LLM ÇAĞRISI (Gemini / OpenAI) + FALLBACK
# =========================================================================== #

def call_llm_for_notification(
    payload: dict, provider: str = "gemini", force_fallback: bool = False, timeout: int = 20,
) -> tuple[dict, str, str | None]:
    """
    Döner: (bildirim_dict, kaynak, hata_mesaji)
      kaynak: "llm" veya "fallback"
      hata_mesaji: fallback'e düşüldüyse sebep (UI'da gösterilir), aksi halde None
    Bu fonksiyon HİÇBİR ZAMAN exception fırlatmaz — her hata yerel şablona
    (fallback_rule_template) yönlendirilir, dashboard asla çökmez.
    """
    if force_fallback:
        return fallback_rule_template(payload), "fallback", "Kullanıcı fallback simülasyonunu manuel olarak etkinleştirdi."

    try:
        if provider == "gemini":
            data = _call_gemini(payload, timeout)
        elif provider == "openai":
            data = _call_openai(payload, timeout)
        else:
            raise ValueError(f"Bilinmeyen sağlayıcı: {provider}")

        _validate_notification_schema(data)
        return data, "llm", None

    except QuotaExceededError as e:
        return fallback_rule_template(payload), "fallback", f"Kota/oran limiti aşıldı: {e}"
    except SchemaValidationError as e:
        return fallback_rule_template(payload), "fallback", f"Model çıktısı şemaya uymadı: {e}"
    except requests.exceptions.Timeout:
        return fallback_rule_template(payload), "fallback", "API zaman aşımına uğradı (timeout)."
    except requests.exceptions.RequestException as e:
        return fallback_rule_template(payload), "fallback", f"Ağ/API hatası: {e}"
    except Exception as e:  # noqa: BLE001 - kasıtlı geniş yakalama: sistem asla çökmemeli
        return fallback_rule_template(payload), "fallback", f"Beklenmeyen hata: {e}"


def _get_api_key(env_name: str) -> str | None:
    """secrets.toml dosyası hiç yoksa Streamlit `StreamlitSecretNotFoundError`
    fırlatır (AttributeError DEĞİLDİR, bu yüzden hasattr() ile yakalanamaz).
    Bu fonksiyon her koşulda (dosya var/yok, anahtar var/yok) güvenli çalışır."""
    try:
        if env_name in st.secrets:
            return st.secrets[env_name]
    except Exception:
        pass  # secrets.toml yok/okunamıyor -> ortam değişkenine düş
    return os.environ.get(env_name)


def _extract_json_block(raw_text: str) -> dict:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "").replace("json", "", 1)
    return json.loads(cleaned.strip())


def _call_gemini(payload: dict, timeout: int) -> dict:
    api_key = _get_api_key("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY tanımlı değil.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    body = {"contents": [{"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}]}
    resp = requests.post(url, json=body, timeout=timeout)

    if resp.status_code == 429:
        raise QuotaExceededError("Gemini API kota/oran limiti (HTTP 429)")
    resp.raise_for_status()

    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _extract_json_block(text)


def _call_openai(payload: dict, timeout: int) -> dict:
    api_key = _get_api_key("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY tanımlı değil.")

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Sadece istenen JSON şemasına uyan geçerli JSON döndür."},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
    }
    resp = requests.post(url, json=body, headers=headers, timeout=timeout)

    if resp.status_code == 429:
        raise QuotaExceededError("OpenAI API kota/oran limiti (HTTP 429)")
    resp.raise_for_status()

    text = resp.json()["choices"][0]["message"]["content"]
    return _extract_json_block(text)


def fallback_rule_template(payload: dict) -> dict:
    """Harici LLM çağrısı BAŞARISIZ olduğunda devreye giren, tamamen yerel,
    deterministik kural tabanlı bildirim üreticisi. Ağ bağlantısı gerektirmez."""
    segment = payload["musteri_baglami"]["segment"]
    urun = payload["musteri_baglami"]["terk_edilen_urun"]
    budget = payload["kisitlar"]["maksimum_butce_tl"]
    cash_forbidden = payload["kisitlar"]["nakit_veya_yuzde_indirim_yasak"]

    templates = {
        "champions": ("Size Özel Bir Sürpriz Hazırladık 🎁", f"{urun} siparişinize VIP hızlı teslimat hediyemiz sizi bekliyor."),
        "loyal_customers": ("Sadakatiniz İçin Teşekkürler 💙", f"{urun} için size özel hızlı kargo ayrıcalığı tanımlandı."),
        "at_risk": ("Sizi Özledik 🙁", f"{urun} için size özel bir kurtarma indirimi hazırladık, kaçırmayın."),
        "cant_loose": ("Son Şans, Sizin İçin! ⏰", f"{urun} için özel indiriminiz sınırlı süre geçerli."),
    }
    default_title, default_body = "Sizin İçin Bir Fırsat Var 🛍️", f"{urun} için özel teklifiniz hazır, hemen inceleyin."
    baslik, mesaj = templates.get(segment, (default_title, default_body))

    if cash_forbidden and ("indirim" in mesaj.lower() or "%" in mesaj):
        mesaj = mesaj  # VIP şablonları zaten indirim ifadesi içermeyecek şekilde tasarlandı

    kupon = _generate_deterministic_coupon(segment, budget)
    return {"baslik": baslik[:40], "mesaj": mesaj[:120], "kupon_kodu": kupon}


def _generate_deterministic_coupon(segment: str, budget: float) -> str:
    digest = hashlib.sha256(f"{segment}-{budget}-{int(time.time() // 3600)}".encode()).hexdigest().upper()
    return f"{digest[:4]}-{digest[4:8]}"


# =========================================================================== #
# 7. MÜŞTERİ PANELİ & MOBİL KİLİT EKRANI MOCKUP'I
# =========================================================================== #

def _pick_abandoned_product(customer_id) -> str:
    """Demo amaçlı: müşteri ID'sine göre deterministik ürün ataması.
    Gerçek sistemde bu, sepet terki / son görüntülenen ürün verisinden gelir."""
    idx = int(hashlib.md5(str(customer_id).encode()).hexdigest(), 16) % len(DEMO_ABANDONED_PRODUCTS)
    return DEMO_ABANDONED_PRODUCTS[idx]


def render_customer_simulation_panel(df: pd.DataFrame, provider: str, force_fallback: bool) -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("##### 🎯 Müşteri Bazlı LLM & Push Bildirim Önizlemesi")

    left, right = st.columns([1.15, 1])

    with left:
        if st.button("🔀 Rastgele Müşteri Seç", use_container_width=True):
            st.session_state["selected_customer_idx"] = random.randint(0, len(df) - 1)

        if "selected_customer_idx" not in st.session_state:
            st.session_state["selected_customer_idx"] = 0

        customer = df.iloc[st.session_state["selected_customer_idx"]]
        abandoned_product = _pick_abandoned_product(customer["Customer ID"])

        seg_badge_class = (
            "badge-vip" if customer["Segment"] in VIP_SEGMENTS
            else "badge-rescue" if customer["Segment"] in RESCUE_SEGMENTS
            else "badge-standard"
        )
        st.markdown(
            f"""**Müşteri ID:** `{customer['Customer ID']}` &nbsp;
            <span class="badge {seg_badge_class}">{SEGMENT_LABELS_TR.get(customer['Segment'], customer['Segment'])}</span>""",
            unsafe_allow_html=True,
        )
        st.write(
            f"Recency: **{int(customer['Recency'])} gün** · "
            f"Ort. Sepet: **₺{customer['ortalama_sepet_tl']:,.2f}** · "
            f"Maks. Bütçe: **₺{customer['maksimum_butce_tl']:,.2f}**"
        )
        st.write(f"🛒 Terk edilen ürün (simüle): *{abandoned_product}*")

        payload = build_llm_prompt_payload(customer, abandoned_product)
        with st.expander("📤 LLM'e Gönderilecek Kısıtlı JSON Prompt Şeması"):
            st.code(json.dumps(payload, ensure_ascii=False, indent=2), language="json")

        if st.button("✨ Bildirimi Üret (LLM veya Fallback)", type="primary", use_container_width=True):
            with st.spinner("Bildirim üretiliyor..."):
                notification, source, error_msg = call_llm_for_notification(
                    payload, provider=provider, force_fallback=force_fallback,
                )
            st.session_state["last_notification"] = notification
            st.session_state["last_source"] = source
            st.session_state["last_error"] = error_msg

        if source_msg := st.session_state.get("last_error"):
            st.warning(f"⚠️ Fallback devrede: {source_msg}")
        elif st.session_state.get("last_source") == "llm":
            st.success("✅ Bildirim canlı LLM çağrısıyla üretildi.")

    with right:
        notification = st.session_state.get("last_notification") or fallback_rule_template(payload)
        source = st.session_state.get("last_source", "fallback")
        render_lock_screen_mockup(notification, source)

    st.markdown("</div>", unsafe_allow_html=True)


def render_lock_screen_mockup(notification: dict, source: str) -> None:
    badge_color = "#22c55e" if source == "llm" else "#f59e0b"
    badge_text = "🟢 LLM Tarafından Üretildi" if source == "llm" else "🟠 Yerel Fallback Şablonu"

    st.markdown(
        f"""
        <div class="phone-frame">
            <div class="phone-notch"></div>
            <div class="phone-time">09:41</div>
            <div class="phone-date">Çarşamba, 16 Eylül</div>
            <div class="notification-card">
                <div class="notif-header">
                    <div class="app-icon">🛍️</div>
                    <div class="app-name">RetailApp <span class="notif-time">şimdi</span></div>
                </div>
                <div class="notif-title">{notification['baslik']}</div>
                <div class="notif-body">{notification['mesaj']}</div>
                <div class="notif-coupon">🎟️ {notification['kupon_kodu']}</div>
            </div>
            <div class="source-badge" style="background:{badge_color}22; color:{badge_color}; border:1px solid {badge_color}55;">
                {badge_text}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================================== #
# 8. ANA UYGULAMA
# =========================================================================== #

def main() -> None:
    configure_page()
    inject_theme_css()

    st.title("🛡️ Margin Guardrail Cockpit")
    st.caption("RFM Segmentasyonu · Marj Koruma Motoru · LLM Destekli Win-Back Bildirim Simülasyonu")

    base_df = load_base_data()
    caps, provider, force_fallback = render_sidebar()
    live_df = recompute_budgets(base_df, caps)

    render_kpi_row(live_df)
    st.write("")
    render_segment_charts(live_df)
    render_budget_table(live_df)
    st.write("")
    render_customer_simulation_panel(live_df, provider, force_fallback)

    st.caption(
        "Not: Demo/gösterim verisiyle çalışıyorsanız 'terk edilen ürün' alanı simülasyon amaçlıdır. "
        "Gerçek ortamda bu alan sepet terki / son görüntülenen ürün verisinden beslenmelidir."
    )


if __name__ == "__main__":
    main()
