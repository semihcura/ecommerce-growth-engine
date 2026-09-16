import datetime as dt
import glob
import os
import pandas as pd

KLASOR = r"C:\Users\semih\Desktop\e-ticaret-ai-motoru"
os.chdir(KLASOR)

# Klasördeki Kaggle dosyasını otomatik tespit et (csv veya xlsx)
dosya_listesi = (
    glob.glob("*.csv") + glob.glob("*.xlsx") + glob.glob("*.xls")
)
hedef_dosya = None

for d in dosya_listesi:
  if "online_retail" in d.lower() or "retail" in d.lower():
    hedef_dosya = d
    break

if not hedef_dosya:
  # Genel tarama: Dashboard veya kod dosyaları haricindeki ilk büyük veri dosyası
  for d in dosya_listesi:
    if not (
        d.startswith("rfm_")
        or d.startswith("app")
        or d.startswith("margin_")
        or d.startswith("process_")
    ):
      hedef_dosya = d
      break

if not hedef_dosya:
  raise FileNotFoundError(
      "Online Retail veri dosyası bulunamadı. Lütfen Kaggle dosyasını klasöre"
      " koyun."
  )

print(f"Tespit edilen veri dosyası okunuyor: {hedef_dosya}...")

if hedef_dosya.endswith(".xlsx") or hedef_dosya.endswith(".xls"):
  df_raw = pd.read_excel(hedef_dosya)
else:
  try:
    df_raw = pd.read_csv(hedef_dosya, encoding="utf-8")
  except UnicodeDecodeError:
    df_raw = pd.read_csv(hedef_dosya, encoding="ISO-8859-1")

print(f"Ham veri satır sayısı: {len(df_raw):,}")

# 1. Pipeline Temizliği
df = df_raw.copy()

# Kolon isimlerindeki boşlukları ve uyumsuzlukları temizle
df.columns = df.columns.str.strip()

# Kolon isim eşleştirmesi
id_col = "Customer ID" if "Customer ID" in df.columns else "CustomerID"
invoice_col = "Invoice" if "Invoice" in df.columns else "InvoiceNo"
price_col = "Price" if "Price" in df.columns else "UnitPrice"

df = df.dropna(subset=[id_col])
df = df[~df[invoice_col].astype(str).str.contains("C", na=False)]
df = df[(df["Quantity"] > 0) & (df[price_col] > 0)]
df["TotalPrice"] = df["Quantity"] * df[price_col]
df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
df[id_col] = df[id_col].astype(int)

print(f"Temizleme sonrası geçerli işlem sayısı: {len(df):,}")

# 2. RFM Metrikleri
ref_date = df["InvoiceDate"].max() + dt.timedelta(days=2)

rfm = df.groupby(id_col).agg({
    "InvoiceDate": lambda d: (ref_date - d.max()).days,
    invoice_col: lambda x: x.nunique(),
    "TotalPrice": lambda p: p.sum(),
})

rfm.columns = ["Recency", "Frequency", "Monetary"]
rfm["ortalama_sepet_tl"] = (rfm["Monetary"] / rfm["Frequency"]).round(2)

# 3. İstatistiksel Dağılım (qcut)
rfm["recency_score"] = pd.qcut(rfm["Recency"], 5, labels=[5, 4, 3, 2, 1])
rfm["frequency_score"] = pd.qcut(
    rfm["Frequency"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]
)
rfm["monetary_score"] = pd.qcut(rfm["Monetary"], 5, labels=[1, 2, 3, 4, 5])

rfm["RF_SCORE"] = (
    rfm["recency_score"].astype(str) + rfm["frequency_score"].astype(str)
)

# 4. Standart 10'lu RFM Matrisi Eşlemesi
seg_map = {
    r"[1-2][1-2]": "hibernating",
    r"[1-2][3-4]": "at_risk",
    r"[1-2]5": "cant_loose",
    r"3[1-2]": "about_to_sleep",
    r"33": "need_attention",
    r"[3-4][4-5]": "loyal_customers",
    r"41": "promising",
    r"51": "new_customers",
    r"[4-5][2-3]": "potential_loyalists",
    r"5[4-5]": "champions",
}

rfm["Segment"] = rfm["RF_SCORE"].replace(seg_map, regex=True)
rfm = rfm.reset_index().rename(columns={id_col: "Customer ID"})

# Dashboard için sadeleştirilmiş çıktı
cikti_kolonlari = [
    "Customer ID",
    "Segment",
    "Recency",
    "Frequency",
    "Monetary",
    "ortalama_sepet_tl",
]
cikis_dosyasi = "rfm_results.csv"
rfm[cikti_kolonlari].to_csv(cikis_dosyasi, index=False)

print(f"\nİşlem tamamlandı!")
print(f"Benzersiz Müşteri Sayısı: {len(rfm):,}")
print(f"'{cikis_dosyasi}' dosyası oluşturuldu.")