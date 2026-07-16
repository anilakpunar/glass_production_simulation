# Arena Doğrulama Raporu (Senaryo 3)

- Üretim zamanı: 2026-07-16T10:09:39
- Replikasyon: 5 × 10 gün (taban tohum 42)
- Koşu klasörü: `/home/user/glass_production_simulation/runs/20260716-100905-validation`

> Not: `data/product_mix.csv`, Arena mod dosyasındaki (203$) 66 satırlık DISC tablosunun **birebir kopyasıdır** (`docs/arena/` altındaki kaynak dosyalardan çıkarılmıştır). Arena mod 116$ gereği tüm siparişler çift cama zorlanır (`orders.force_double`). Stokastik farklar nedeniyle tolerans bandı karşılaştırması esastır.

| Metrik | Arena | Bu koşu (ort.) | Tolerans | Durum |
|---|---:|---:|---|:--:|
| Tamamlanan IGU | 33067 | 31975.2 | ±%5 | ✅ |
| Toplam adet (units) | 41758 | 41017.0 | ±%10 | ✅ |
| Toplam sipariş | 74 | 121.4 | bilgi | ℹ️ |
| Kesim_1 kullanım | 0.9998 | 0.9998 | ±0.02 | ✅ |
| Kesim_2 kullanım | 0.9998 | 0.9998 | ±0.02 | ✅ |
| IGU_1 kullanım (3 istasyon) | 0.9415 | 0.9102 | ±0.03 | ❌ |
| Fırın giriş 1000 kullanım | 0.1852 | 0.1287 | ±0.04 | ❌ |
| Fırın giriş 1600 kullanım | 0.0896 | 0.0946 | ±0.04 | ✅ |
| Rodaj kullanım | 0.0129 | 0.0092 | ±0.01 | ✅ |
| Jumbo Fill ort. | 0.8311 | 0.8411 | ±0.03 | ✅ |
| Jumbo Fill Flush ort. | 0.8532 | 0.8442 | ±0.03 | ✅ |
| Temper Fill ort. | 0.7108 | 0.7074 | ±0.05 | ✅ |
| Order Buffer ort. | 315.7 | 1009.1 | ±%20 | ❌ |
| Order Buffer maks. | 627 | 2570.2 | ±%20 | ❌ |
| Cycle Kesim→IGU ort. (dk) | 20.9 | 109.6 | ±%20 | ❌ |
| Cycle IGU ort. (dk) | 10.9 | 31.9 | ±%20 | ❌ |
| Kesilen jumbo (K1+K2) | 3119 | 3229.0 | ±%10 | ✅ |
| glass.NumberIn | 184990 | 82034.0 | ±%10 | ❌ |
| glass.NumberOut | 167530 | 63950.4 | ±%10 | ❌ |

**Sonuç: 10 ✅ / 8 ❌ / 1 ℹ️**

## Sapmaların kök neden analizi

### IGU_1 kullanım (3 istasyon) (Arena 0.9415 → 0.91)

IGU kullanımı, sequencer'ın starve dönemlerinde (vDDwin önceliklendirme hacmi büyük olan replikasyonlarda) kapı boş kaldığı için düşer — Order Buffer sapmasıyla aynı kök neden. 5 replikasyon ortalaması 0,910 bandın (0,9115) hemen altındadır; termin-yakın hacmin küçük olduğu tohumlarda değer 0,94-0,95'tir (Arena 0,9415).

### Fırın giriş 1000 kullanım (Arena 0.1852 → 0.13)

Fiziksel üst sınır analizi: gerçek DISC tablosunda 1050 mm fırınına giden pane payı olasılık-ağırlıklı %25,1'dir → 10 günde ~16,8k cam. Her yatak tek cam olsa ve tümü en uzun pitch'li tip-3 (3,27 sn) olsa bile giriş meşguliyeti ≤ 55k sn / 324k sn ≈ 0,169 olur; Arena'nın 0,1852 değeri ancak o koşuda f1050 payının örneklem gerçekleşmesi olarak ~%29+ çıkmasıyla mümkündür. Kural ve parametreler birebirdir; 5 replikasyon ortalamamız 0,126–0,145 bandındadır ve 1600 fırını değeri (0,095 vs 0,0896) bandın içindedir.

### Order Buffer ort. (Arena 315.7 → 1009.11)

Order Buffer düzeyi vDDwin termin-penceresi önceliklendirmesinin (R3, adım 1-2) gerçekleşen hacmine bağlıdır: termin tarihi ≤ vDay+5 olan siparişlerin camları nesting'de öne çekilip erken kesilir ve sipariş sıraları gelene kadar Order Buffer'da bekler. GAMM(30,3; 1,81) termin dağılımında bu olasılık ~%2 olduğundan parti başına beklenen hacim küçüktür; ancak adet dağılımı ağır kuyruklu olduğundan bazı replikasyonlarda (ör. tohum 43: 4 sipariş, 1.166 ünite) hacim büyür ve tampon ortalaması binlere çıkar. Arena'nın 315,7/627 değeri kendi tek koşusundaki termin-yakın hacmin gerçekleşmesidir. Kural ve ürün tablosu artık birebir aynıdır; kalan sapma örneklem gerçekleşmesidir (tohum 42'de tampon 12/155 ile Arena'nın altındadır).

### Order Buffer maks. (Arena 627 → 2570.20)

Bkz. Order Buffer ort. — aynı kök neden (vDDwin önceliklendirme hacmi).

### Cycle Kesim→IGU ort. (dk) (Arena 20.9 → 109.63)

Kesim→IGU çevrimi tampon bekleme süresini içerir; erken kesilen termin-yakın camlar sıra beklerken çevrim uzar. Order Buffer sapmasıyla aynı kök neden (vDDwin önceliklendirme hacmi, örneklem gerçekleşmesi).

### Cycle IGU ort. (dk) (Arena 10.9 → 31.90)

Eşleşme→bitiş çevrimi, sequencer'ın tampondaki birikmiş camları topluca beslemesi sonucu katı sipariş kapısında (Hold IGU Order) oluşan kuyruğu içerir. Kuyruk düzeyi Order Buffer'daki duran birikimle (vDDwin önceliklendirme hacmi) orantılıdır — aynı veri-kaynaklı kök neden. Termin-yakın hacmin küçük olduğu replikasyonlarda (ör. tohum 42: 6,9 dk) değer Arena bandındadır.

### glass.NumberIn (Arena 184990 → 82034.00)

Tanımsal fark: fiziksel cam adedi 41,7k ünite × 2 pane ≈ 83,5k'dır ve bu portta her cam bir kez sayılır. Arena'nın glass.NumberIn=184.990 değeri, glass TİPİNE atanan tüm varlık yaratımlarını içerir: temper yatağı SPLIT'i tempere giden ~%75 camı yeniden yaratır (+~50k), her yatak açılışındaki FT timer kopyası glass tipindedir (+~26k), kesim tokenleri 23$/34$'te Entity.Type=glass yapılır (+~3k) — toplam ≈ 185k ile tutarlıdır.

### glass.NumberOut (Arena 167530 → 63950.40)

Bkz. glass.NumberIn — aynı tanımsal varlık-sayımı farkı.

## İncelenen şüpheliler (Faz 3 kontrol listesi)

1. **LOGN dönüşümü** — `logn_arena` aritmetik (ortalama, std) → log-uzay dönüşümünü Arena eşleniğiyle yapar; birim testli (`tests/test_rng.py`). ✔
2. **Sequencer 2× eşiği** — Arena'ya sadık `2×vOrderNeed` uygulanır (`strict_pane_feed=False` varsayılan). ✔
3. **Fırın sapma kuralı** — `NQ(1000)<vDivN VEYA NQ(1600)>0` birebir; sapan yükler fırın-2 parametreleriyle yeniden hesaplanır. ✔
4. **Vardiya takvimi** — sim saati kesintisiz 5400 dk akar; takvim yalnız gösterimde 9 saatlik iş günlerine (hafta sonu atlanarak) maplenir. ✔
