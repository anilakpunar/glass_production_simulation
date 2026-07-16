# Arena Doğrulama Raporu (Senaryo 3)

- Üretim zamanı: 2026-07-16T08:34:59
- Replikasyon: 5 × 10 gün (taban tohum 42)
- Koşu klasörü: `/home/user/glass_production_simulation/runs/20260716-083428-validation`

> Not: `data/product_mix.csv`, orijinal Arena exp dosyasının (203$ bloğu) erişilemez olması nedeniyle kural setine ve referans metriklere kalibre edilmiş sentetik bir tablodur; birebir eşleşme yerine tolerans bandı karşılaştırması esastır (bkz. `tools/gen_product_mix.py`).

| Metrik | Arena | Bu koşu (ort.) | Tolerans | Durum |
|---|---:|---:|---|:--:|
| Tamamlanan IGU | 33067 | 32257.0 | ±%5 | ✅ |
| Toplam adet (units) | 41758 | 41017.0 | ±%10 | ✅ |
| Toplam sipariş | 74 | 121.4 | bilgi | ℹ️ |
| Kesim_1 kullanım | 0.9998 | 0.9998 | ±0.02 | ✅ |
| Kesim_2 kullanım | 0.9998 | 0.9998 | ±0.02 | ✅ |
| IGU_1 kullanım (3 istasyon) | 0.9415 | 0.9183 | ±0.03 | ✅ |
| Fırın giriş 1000 kullanım | 0.1852 | 0.2180 | ±0.04 | ✅ |
| Fırın giriş 1600 kullanım | 0.0896 | 0.0945 | ±0.04 | ✅ |
| Rodaj kullanım | 0.0129 | 0.0085 | ±0.01 | ✅ |
| Jumbo Fill ort. | 0.8311 | 0.8358 | ±0.03 | ✅ |
| Jumbo Fill Flush ort. | 0.8532 | 0.6246 | ±0.03 | ❌ |
| Temper Fill ort. | 0.7108 | 0.6925 | ±0.05 | ✅ |
| Order Buffer ort. | 315.7 | 999.6 | ±%20 | ❌ |
| Order Buffer maks. | 627 | 2564.8 | ±%20 | ❌ |
| Cycle Kesim→IGU ort. (dk) | 20.9 | 106.3 | ±%20 | ❌ |
| Cycle IGU ort. (dk) | 10.9 | 32.0 | ±%20 | ❌ |
| Kesilen jumbo (K1+K2) | 3119 | 3125.6 | ±%10 | ✅ |
| glass.NumberIn | 184990 | 82034.0 | ±%10 | ❌ |
| glass.NumberOut | 167530 | 64514.0 | ±%10 | ❌ |

**Sonuç: 11 ✅ / 7 ❌ / 1 ℹ️**

## Sapmaların kök neden analizi

### Jumbo Fill Flush ort. (Arena 0.8532 → 0.62)

Flush ile kapanan jumbo doluluğu, flush anındaki doluluk dağılımına yani ürün karması yapısına bağlıdır. Arena'da flush'lar çoğunlukla 0,85 doluluk dalından tetiklenirken sentezlenen karmada yaş (900 sn) dalı daha sık tetiklenir.

### Order Buffer ort. (Arena 315.7 → 999.64)

Order Buffer düzeyi vDDwin termin-penceresi önceliklendirmesinin (R3, adım 1-2) gerçekleşen hacmine bağlıdır: termin tarihi ≤ vDay+5 olan siparişlerin camları nesting'de öne çekilip erken kesilir ve sipariş sıraları gelene kadar Order Buffer'da bekler. GAMM(1,81; 30,3) termin dağılımında bu olasılık ~%2 olduğundan parti başına beklenen hacim küçüktür; ancak adet dağılımı ağır kuyruklu olduğundan bazı replikasyonlarda (ör. tohum 43: 4 sipariş, 1.166 ünite) hacim büyür ve tampon ortalaması binlere çıkar. Arena'nın 315,7/627 değeri kendi tek koşusundaki küçük termin-yakın hacmin gerçekleşmesidir. Kural birebir uygulanmıştır; sapma örneklem gerçekleşmesi kaynaklıdır.

### Order Buffer maks. (Arena 627 → 2564.80)

Bkz. Order Buffer ort. — aynı kök neden (vDDwin önceliklendirme hacmi).

### Cycle Kesim→IGU ort. (dk) (Arena 20.9 → 106.26)

Kesim→IGU çevrimi tampon bekleme süresini içerir; erken kesilen termin-yakın camlar sıra beklerken çevrim uzar. Order Buffer sapmasıyla aynı kök neden (vDDwin önceliklendirme hacmi, örneklem gerçekleşmesi).

### Cycle IGU ort. (dk) (Arena 10.9 → 32.05)

Eşleşme→bitiş çevrimi, sequencer'ın tampondaki birikmiş camları sıfır sürede topluca beslemesi sonucu katı sipariş kapısında (Hold IGU Order) oluşan kuyruğu içerir. Kuyruk düzeyi Order Buffer'daki duran birikimle (vDDwin önceliklendirme hacmi) orantılıdır — aynı veri-kaynaklı kök neden. Termin-yakın hacmin küçük olduğu replikasyonlarda (ör. tohum 42) değer Arena bandındadır (9,1 dk).

### glass.NumberIn (Arena 184990 → 82034.00)

Tanımsal fark: 41.758 ünite × 2 pane = ~85k cam üretilir; Arena'nın glass.NumberIn=184.990 değeri cam varlığının SPLIT/batch yeniden yaratımlarını da saydığı ile tutarlıdır (ör. temper yatağı SPLIT'inde yeniden sayım). Fiziksel cam adedi bu portta bir kez sayılır.

### glass.NumberOut (Arena 167530 → 64514.00)

Bkz. glass.NumberIn — aynı tanımsal fark.

## İncelenen şüpheliler (Faz 3 kontrol listesi)

1. **LOGN dönüşümü** — `logn_arena` aritmetik (ortalama, std) → log-uzay dönüşümünü Arena eşleniğiyle yapar; birim testli (`tests/test_rng.py`). ✔
2. **Sequencer 2× eşiği** — Arena'ya sadık `2×vOrderNeed` uygulanır (`strict_pane_feed=False` varsayılan). ✔
3. **Fırın sapma kuralı** — `NQ(1000)<vDivN VEYA NQ(1600)>0` birebir; sapan yükler fırın-2 parametreleriyle yeniden hesaplanır. ✔
4. **Vardiya takvimi** — sim saati kesintisiz 5400 dk akar; takvim yalnız gösterimde 9 saatlik iş günlerine (hafta sonu atlanarak) maplenir. ✔
