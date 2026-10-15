import streamlit as st
import pandas as pd
import numpy as np
import networkx as nx
import osmnx as ox
import folium
import math
from streamlit_folium import st_folium

st.set_page_config(page_title="Avcılar Afet Lojistik - Gerçek Sokak Ağı", layout="wide")

st.title("🚨 Avcılar Dinamik Afet Karar Destek Sistemi (OSMnx)")
st.markdown("Bu sistem, Avcılar'ın **gerçek cadde ve sokak ağını** anlık çekerek, deprem anında enkaz riskine göre Google Maps benzeri navigasyon sağlar.")

# 1. GERÇEK SOKAK AĞINI İNDİRME
# Sadece ilk açılışta çalışır, haritayı bilgisayarın hafızasına kaydeder.
@st.cache_resource(show_spinner="Avcılar gerçek sokak ağı indiriliyor... (Bu işlem sadece 1 kere yapılır, yaklaşık 1 dakika sürebilir)")
def avcilar_sokak_agini_indir():
    ox.settings.use_cache = True
    # Avcılar'ın sadece araba/lojistik girebilen yol ağını çekiyoruz
    G = ox.graph_from_place("Avcılar, Istanbul, Turkey", network_type="drive")
    # Yönlü grafiğe çeviriyoruz (Dijkstra rotalaması için gerekli)
    G = ox.utils_graph.get_digraph(G, weight='length')
    return G

# 2. SOKAKLARA RİSK (ENKAZ) ATAMA SİMÜLASYONU
@st.cache_data
def afet_senaryosu_uygula(_G_base, deprem_siddeti):
    G = _G_base.copy()
    np.random.seed(42) 
    
    for u, v, data in G.edges(data=True):
        uzunluk = data.get('length', 10)
        
        # Simülasyon: Rastgele bina katı ve yaş kırılganlığı (Gerçekte CBS'den alınır)
        bina_kati = np.random.choice([3, 5, 8, 10], p=[0.3, 0.4, 0.2, 0.1])
        mahalle_riski = np.random.choice([3, 7, 10], p=[0.2, 0.5, 0.3])
        yol_genisligi = np.random.choice([5, 8, 12]) 
        
        W_v, W_k, W_e = 0.40, 0.40, 0.20
        
        siddet_carpani = 1.0
        if deprem_siddeti > 7.0:
            siddet_carpani = 1 + (deprem_siddeti - 7.0) * 2.5
            
        risk_skoru = ((mahalle_riski * W_v) + (bina_kati * W_k) - (yol_genisligi * W_e)) * siddet_carpani
        risk_skoru = max(1, risk_skoru)
        
        # Riske göre yol durumu
        if risk_skoru > 19:
            durum = 'Kırmızı'
            maliyet = float('inf') # Geçilemez (Enkaz altında)
        elif risk_skoru > 11:
            durum = 'Sarı'
            maliyet = uzunluk * (risk_skoru / 2) # Geçilebilir ama çok yavaş
        else:
            durum = 'Yeşil'
            maliyet = uzunluk # Güvenli ve açık
            
        data['durum'] = durum
        data['weight'] = maliyet # Dijkstra için maliyet ataması
        
    return G

# 3. EXCEL'DEN TOPLANMA ALANLARINI ÇEKME
@st.cache_data
def toplanma_alanlarini_yukle():
    try:
        df = pd.read_excel("Yeni Microsoft Excel Çalışma Sayfası (2).xlsx")
        noktalar = []
        for _, satir in df.iterrows():
            isim = str(satir['Alan_Adi']).strip()
            enlem_str = str(satir['Enlem']).replace(',', '.').replace('.', '').strip()
            boylam_str = str(satir['Boylam']).replace(',', '.').replace('.', '').strip()
            enlem = float(f"{enlem_str[:2]}.{enlem_str[2:]}")
            boylam = float(f"{boylam_str[:2]}.{boylam_str[2:]}")
            noktalar.append({'isim': isim, 'lat': enlem, 'lon': boylam})
        return noktalar
    except:
        st.error("Excel verisi bulunamadı!")
        return []

# --- ARAYÜZ ---
G_base = avcilar_sokak_agini_indir()
noktalar = toplanma_alanlarini_yukle()

col1, col2 = st.columns([1, 3])

with col1:
    st.header("⚙️ Navigasyon Paneli")
    deprem_siddeti = st.slider("Deprem Şiddeti (Mw)", 5.0, 8.0, 7.5, 0.1)
    
    if noktalar:
        isimler = [n['isim'] for n in noktalar]
        baslangic_isim = st.selectbox("Bulunduğunuz Konum (Başlangıç)", isimler, index=0)
        hedef_isim = st.selectbox("Gitmek İstenen Safe Zone (Hedef)", isimler, index=1)
        hesapla_btn = st.button("🗺️ Toplanma Alanı Bul (Rota Çiz)", use_container_width=True)

with col2:
    # Ağı seçilen deprem şiddetine göre simüle et
    G_guncel = afet_senaryosu_uygula(G_base, deprem_siddeti)
    
    # Haritayı oluştur (OpenStreetMap sokak görünümü)
    m = folium.Map(location=[40.98, 28.72], zoom_start=14, tiles="OpenStreetMap")
    
    if noktalar:
        baslangic = next(n for n in noktalar if n['isim'] == baslangic_isim)
        hedef = next(n for n in noktalar if n['isim'] == hedef_isim)
        
        # Başlangıç ve Bitiş İkonları
        folium.Marker([baslangic['lat'], baslangic['lon']], tooltip="BAŞLANGIÇ: " + baslangic_isim, icon=folium.Icon(color='green', icon='user')).add_to(m)
        folium.Marker([hedef['lat'], hedef['lon']], tooltip="HEDEF: " + hedef_isim, icon=folium.Icon(color='blue', icon='flag')).add_to(m)

        if 'hesapla_btn' in locals() and hesapla_btn:
            # Koordinatlara en yakın GERCÇEK SOKAK kavşaklarını bul
            orig_node = ox.distance.nearest_nodes(G_guncel, baslangic['lon'], baslangic['lat'])
            dest_node = ox.distance.nearest_nodes(G_guncel, hedef['lon'], hedef['lat'])
            
            # KAPANAN (Kırmızı) yolları haritada gösterelim ki kullanıcı görsün!
            kapanan_yollar = []
            for u, v, data in G_guncel.edges(data=True):
                if data['durum'] == 'Kırmızı':
                    u_lat, u_lon = G_guncel.nodes[u]['y'], G_guncel.nodes[u]['x']
                    v_lat, v_lon = G_guncel.nodes[v]['y'], G_guncel.nodes[v]['x']
                    kapanan_yollar.append([(u_lat, u_lon), (v_lat, v_lon)])
            
            # Haritayı yormamak için ilk 300 enkazı çiziyoruz
            for yol in kapanan_yollar[:300]:
                folium.PolyLine(yol, color='red', weight=3, opacity=0.6, tooltip="KAPALI YOL (ENKAZ)").add_to(m)
            
            try:
                # Algoritma: Sokak sokak köşeleri dönerek güvenli rotayı hesapla
                rota = nx.shortest_path(G_guncel, orig_node, dest_node, weight='weight')
                
                # Rota koordinatlarını çıkar ve Google Maps mavisiyle çiz
                rota_coords = [(G_guncel.nodes[n]['y'], G_guncel.nodes[n]['x']) for n in rota]
                folium.PolyLine(rota_coords, color='#00a2ff', weight=6, opacity=0.9, tooltip="Önerilen Güvenli Rota").add_to(m)
                
                st.success("✅ Rota çizildi! Algoritma kırmızıya dönen (enkaz altındaki) sokaklardan başarıyla kaçındı.")
                
            except nx.NetworkXNoPath:
                st.error("🚨 KRİTİK UYARI: Deprem şiddeti o kadar yüksek ki, bu iki alan arasındaki tüm sokaklar enkaz altında! Algoritma güvenli rota bulamadı, lütfen başka bir alan seçin.")
        
    # Haritayı Ekrana Bas
    st_folium(m, width=900, height=600)
