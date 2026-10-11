import streamlit as st
import pandas as pd
import numpy as np
import networkx as nx
import math
import folium
from streamlit_folium import st_folium

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Avcılar Afet Lojistik Simülasyonu", layout="wide")

st.title("🚨 Avcılar Dinamik Afet Karar Destek Sistemi")
st.markdown("Bu sistem, 1999 öncesi uydu verileri ve bina kat haritalarını analiz ederek, deprem sonrası **gerçek zamanlı en güvenli toplanma alanı rotasını** hesaplar.")

# --- FONKSİYONLAR ---
def haversine_mesafe(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = math.sin(math.radians(lat2 - lat1) / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lon2 - lon1) / 2.0) ** 2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def risk_skoru_hesapla(mesafe, mahalle_riski, bina_kati, yol_genisligi, deprem_siddeti):
    W_v, W_k, W_e = 0.40, 0.40, 0.20
    
    # Deprem şiddetine göre riskin üstel artışı
    siddet_carpani = 1.0
    if deprem_siddeti > 7.0:
        siddet_carpani = 1 + (deprem_siddeti - 7.0) * 2
        
    kapanma_indeksi = ((mahalle_riski * W_v) + (bina_kati * W_k) - (yol_genisligi * W_e)) * siddet_carpani
    kapanma_indeksi = max(1, kapanma_indeksi)
    return mesafe * kapanma_indeksi

@st.cache_data
def agi_hazirla(deprem_siddeti):
    try:
        df = pd.read_excel("Yeni Microsoft Excel Çalışma Sayfası (2).xlsx")
    except:
        return None, None

    G = nx.Graph()
    risk_sozlugu = {
        'Merkez': 10, 'Ambarlı': 10, 'Denizköşkler': 10, 'Gümüşpala': 10,
        'Mustafa Kemal Paşa': 7, 'Üniversite': 7, 'Cihangir': 7,
        'Firuzköy': 3, 'Yeşilkent': 3, 'Tahtakale': 3
    }
    
    noktalar = []
    for index, satir in df.iterrows():
        isim = str(satir['Alan_Adi']).strip()
        enlem = float(str(satir['Enlem']).replace(',', '.').replace('.', '').strip()[:2] + "." + str(satir['Enlem']).replace(',', '.').replace('.', '').strip()[2:])
        boylam = float(str(satir['Boylam']).replace(',', '.').replace('.', '').strip()[:2] + "." + str(satir['Boylam']).replace(',', '.').replace('.', '').strip()[2:])
        
        atanan_mahalle = 'Merkez'
        for m in risk_sozlugu.keys():
            if m.lower() in isim.lower():
                atanan_mahalle = m
                break
                
        G.add_node(isim, lat=enlem, lon=boylam, mahalle=atanan_mahalle)
        noktalar.append({'isim': isim, 'lat': enlem, 'lon': boylam, 'mahalle': atanan_mahalle})

    np.random.seed(42) # Tutarlı simülasyon
    for i in range(len(noktalar)):
        for j in range(i + 1, len(noktalar)):
            n1, n2 = noktalar[i], noktalar[j]
            mesafe = haversine_mesafe(n1['lat'], n1['lon'], n2['lat'], n2['lon'])
            
            if mesafe < 1200: # 1.2 km bağlantı ağı
                mahalle_riski = risk_sozlugu[n1['mahalle']]
                bina_kati = np.random.choice([3, 5, 8], p=[0.3, 0.5, 0.2])
                yol_genisligi = np.random.choice([7, 10, 15])
                
                agirlik = risk_skoru_hesapla(mesafe, mahalle_riski, bina_kati, yol_genisligi, deprem_siddeti)
                risk_katsayisi = agirlik / mesafe
                
                # ENKAZ SİMÜLASYONU: Çok riskli yolları ağdan tamamen kopar (Kapat)
                if risk_katsayisi > 15:
                    continue 
                    
                G.add_edge(n1['isim'], n2['isim'], weight=agirlik, gercek_mesafe=mesafe, risk_katsayisi=risk_katsayisi)

    return G, noktalar

# --- ARAYÜZ KONTROLLERİ VE EKRAN ---
col1, col2 = st.columns([1, 3])

with col1:
    st.header("⚙️ Simülasyon Paneli")
    deprem_siddeti = st.slider("Deprem Şiddeti (Mw)", min_value=5.0, max_value=8.0, value=7.0, step=0.1)
    
    G, noktalar = agi_hazirla(deprem_siddeti)
    
    if G and noktalar:
        isimler = [n['isim'] for n in noktalar]
        baslangic = st.selectbox("Bulunduğunuz Konum (Başlangıç)", isimler, index=0)
        hedef = st.selectbox("Gitmek İstenen Safe Zone (Hedef)", isimler, index=1)
        hesapla_btn = st.button("🚀 En Güvenli Rotayı Bul", use_container_width=True)
    else:
        st.error("Lütfen Excel dosyanızı kontrol edin!")

with col2:
    if G and noktalar:
        # Haritayı oluştur (Avcılar Merkezi)
        m = folium.Map(location=[40.98, 28.72], zoom_start=13, tiles="CartoDB positron")
        
        # Riskli/Güvenli Yol Ağını Çiz
        for u, v, data in G.edges(data=True):
            lat1, lon1 = G.nodes[u]['lat'], G.nodes[u]['lon']
            lat2, lon2 = G.nodes[v]['lat'], G.nodes[v]['lon']
            risk = data['risk_katsayisi']
            
            renk = 'red' if risk > 10 else 'orange' if risk > 6 else 'green'
            folium.PolyLine([(lat1, lon1), (lat2, lon2)], color=renk, weight=1, opacity=0.3).add_to(m)

        # Toplanma Alanları
        for n in noktalar:
            folium.CircleMarker([n['lat'], n['lon']], radius=4, color='blue', fill=True, fill_color='blue', fill_opacity=0.6, tooltip=n['isim']).add_to(m)
            
        if 'hesapla_btn' in locals() and hesapla_btn:
            try:
                # Dijkstra Optimizasyonu
                guvenli_rota = nx.dijkstra_path(G, source=baslangic, target=hedef, weight='weight')
                
                rota_kordinatlari = []
                toplam_mesafe = 0
                for i in range(len(guvenli_rota)-1):
                    durak1, durak2 = guvenli_rota[i], guvenli_rota[i+1]
                    lat1, lon1 = G.nodes[durak1]['lat'], G.nodes[durak1]['lon']
                    lat2, lon2 = G.nodes[durak2]['lat'], G.nodes[durak2]['lon']
                    
                    rota_kordinatlari.append((lat1, lon1))
                    if i == len(guvenli_rota)-2: rota_kordinatlari.append((lat2, lon2))
                        
                    toplam_mesafe += G.get_edge_data(durak1, durak2)['gercek_mesafe']
                    
                folium.PolyLine(rota_kordinatlari, color='blue', weight=5, opacity=0.8).add_to(m)
                folium.Marker([G.nodes[baslangic]['lat'], G.nodes[baslangic]['lon']], icon=folium.Icon(color='green', icon='play')).add_to(m)
                folium.Marker([G.nodes[hedef]['lat'], G.nodes[hedef]['lon']], icon=folium.Icon(color='red', icon='stop')).add_to(m)
                
                st.success(f"✅ Rota Başarıyla Çizildi! Tahmini Fiziksel Mesafe: {toplam_mesafe:.0f} metre")
                
            except nx.NetworkXNoPath:
                st.error("🚨 DİKKAT: Seçilen deprem şiddetinde binaların yıkılması sebebiyle bu iki nokta arasındaki tüm güvenli koridorlar kapanmıştır! Lütfen farklı bir Safe Zone seçin.")

        st_folium(m, width=900, height=600)