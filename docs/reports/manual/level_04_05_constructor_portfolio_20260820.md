# Evidence Constructor Portfolio Level 4–5 — 2026-08-20

- Quyết định: **NOT_PROMOTED**.
- Portfolio thử Best Fit và MES trong cùng request rồi chỉ giữ nghiệm hợp lệ tốt hơn.
- `success_rate=1.0` chỉ xác nhận nghiệm cuối hợp lệ; nó không tự động đồng nghĩa đủ điều kiện promotion.

## Kết quả gate

| Level | VALID | Deterministic | WIN theo lượt | Runtime median / Best Fit | Memory p95 | Trạng thái |
|---|---:|---:|---:|---:|---:|---|
| Level 4 | 252/252 | 84/84 | 108 | 1.760× | -0.62% | **PASS** |
| Level 5 | 252/252 | 83/84 | 107 | 2.219× | -2.51% | **FAIL** |

## Kết luận

Level 4 đạt gate riêng. Level 5 không đạt vì chỉ có 83/84 nhóm deterministic và runtime median bằng 2,219 lần Best Fit, vượt trần 1,8 lần.
Theo protocol đã khóa, cả hai Level phải cùng đạt. Portfolio vì vậy không được mở trên UI, không trở thành mặc định và không được đưa vào `develop`.

## Bài Level 5 không deterministic

- Input: stable-random seed 307, 500 kiện, repeat 3.
- MES trả `TIME_LIMIT`; Best Fit incumbent hợp lệ được giữ.
- Wall runtime khoảng 1.061 giây so với deadline 180 giây.
- Hai repeat đầu chọn MES với 20 container; repeat 3 giữ Best Fit với 22 container.

## Provenance

- Commit nguồn sạch: `7a26ea157af0309eb61e764c9540ca7f6e66bf52`.
- `20260820T040042102821Z__level_04__benchmark_corpus__level_04_validated_constructor_portfolio_random_v1__seed42`:
  - `manifest.json` SHA-256: `f28a492af866109b7b20db666eee720bd3ae009ff25db54b54989759a3b2b733`
  - `results.csv` SHA-256: `b4a45c4cfda9e923a6482aa578f27020db15f421e07f6a8e79fb162b3974279c`
  - `constructor_portfolio_comparison.csv` SHA-256: `cfd6e4b0404f4e1adb8c919db23b306e503b20e4f7fd363717e1ef3094674dca`
  - `determinism_evidence.csv` SHA-256: `4cb3551297ac760ff752fc4191823c879318d2c3cd48676ec9f4e894df5ac5f4`
- `20260820T042410896243Z__level_04__benchmark_corpus__level_04_validated_constructor_portfolio_stress_v1__seed42`:
  - `manifest.json` SHA-256: `39b334c01c669fbfcf2a488f627c39687c6b2d1a2235ad6f2e319976244ab4a3`
  - `results.csv` SHA-256: `635ab31a8dd4556bdab6f52e69162840fef73cbd2da2dcd696ff9276e4c62b1e`
  - `constructor_portfolio_comparison.csv` SHA-256: `5a4ec4b05bfa2838471b8f044eb0c8b4ca3c91f0220e8b8f151a78fc69735254`
  - `determinism_evidence.csv` SHA-256: `3f2c07bc5733b0be84ac8e39401b6e49cae3da8328c405d6b7312f06f2cac51c`
- `20260820T043226893356Z__level_04__benchmark_corpus__level_04_validated_constructor_portfolio_prefix_v1__seed42`:
  - `manifest.json` SHA-256: `d00f1752106b5e71fb2a47abc6a305222761b9705c6a53911a7dbf066a90cb8c`
  - `results.csv` SHA-256: `d682ce0f41bf97801771f98bfc91ede5021f831a64a6d51541319b4b208d0e58`
  - `constructor_portfolio_comparison.csv` SHA-256: `10183350099add7fa7f6831a6c601d0d9191b7cfc770ad53c190d7e7a296a7f8`
  - `determinism_evidence.csv` SHA-256: `2933c555d9b93388aad83b8c0b0e4cac05dd0a971b1e434c857d723684d91006`
- `20260820T043456901393Z__level_05__benchmark_corpus__level_05_validated_constructor_portfolio_random_v1__seed42`:
  - `manifest.json` SHA-256: `d254b427bb9e3d8b04ad0ac55ddda34b967e6991638b1ff17c1402be6880b675`
  - `results.csv` SHA-256: `a5d915627d4509c70fd913f5d9477efc4d105f8ec21515ffa097e5153c8e6c84`
  - `constructor_portfolio_comparison.csv` SHA-256: `771c91e0aa30539fd995fc125940129f10dad40e80fe49e883cf7339b10b1f50`
  - `determinism_evidence.csv` SHA-256: `44a4a73fb87ae3bf0af0d51b7038996bf1bb4004bb4982f29c62ec87a0051d03`
- `20260820T051122933718Z__level_05__benchmark_corpus__level_05_validated_constructor_portfolio_stress_v1__seed42`:
  - `manifest.json` SHA-256: `f50d89bf888af8dcd23bfad1590bc2c800ab40d0ccd723067e9773fe29791812`
  - `results.csv` SHA-256: `e4a36c1b6bf01a41730881b99c77fccc4a31fcad1d89cdff1747b9702baf5e1c`
  - `constructor_portfolio_comparison.csv` SHA-256: `1e62bd957c5fdfe9c8f288bef4984bba2ecc59271b28e1f5e290665b8fddd560`
  - `determinism_evidence.csv` SHA-256: `29d1ce365acd90dcdb2cd54f51dd2c60b2067463ad58413e41ce32183ca5ccd9`
- `20260820T052104757593Z__level_05__benchmark_corpus__level_05_validated_constructor_portfolio_prefix_v1__seed42`:
  - `manifest.json` SHA-256: `c8f095e544081cc0244b92777aec9bfeaa967f49a6cf80b39e63faa62d011a24`
  - `results.csv` SHA-256: `faaa5051fbb5f91ee0be2201faad1a0c596671ba1d1826ada43781dc53da37fd`
  - `constructor_portfolio_comparison.csv` SHA-256: `95d54aaadf7aaa8d1e11243207f9848ff8054e09ccac1c9642f5090696761446`
  - `determinism_evidence.csv` SHA-256: `db1b7de8d75a00e3e1e4e9e69133c16fc1073df8faf8d73d87bd1da6978b6f5b`
- Baseline memory được khóa từ các run phân phối đã nghiệm thu:
  - `20260814T094253684243Z__level_04__benchmark_corpus__level_04_generated_1k_500_random_v2_candidate__seed42`: manifest `df824665f3b5ceba6e86428d2eb5ac6ec640f28915686995be7c793d5dd418e2`, results `a38945a4167a80054140005c9c080674ab23934b0ca3ffb75ed0343db6df7001`.
  - `20260814T094322739352Z__level_04__benchmark_corpus__level_04_generated_1k_500_stress_v2_candidate__seed42`: manifest `e1bd858a786862dadb13aaee574427563b6d96068848cda009e810e7b828d5b9`, results `d72d6633e6d083662ef4180674eb4e0cc9d96f108460acff0dd66abf84824b30`.
  - `20260814T094346306898Z__level_04__benchmark_corpus__level_04_generated_1k_500_prefix_regression_v2__seed42`: manifest `521a876e0f680ba089f21be102535b29dc22456eb755ac0b03086a9c4283f46c`, results `5b21901bf57f9a5ee0adcc41639bc525fb0be510a983cf862c28b8d7eeb5e459`.
  - `20260814T084722235547Z__level_05__benchmark_corpus__level_05_generated_1k_500_random_v2_candidate__seed42`: manifest `fcd74bdec077349638ece01ca5203a0ab84fb11f0ba4c9a7eca8dd31c806de1a`, results `d89ac8c2981320cf36c3ace29085a24ea6655666ba822b57d854c8236141c6de`.
  - `20260814T094359815238Z__level_05__benchmark_corpus__level_05_generated_1k_500_stress_v2_candidate__seed42`: manifest `49f2294ffedbb99ce03304da983030e01ab4bbcd7562a4a5541048bbb14f3a0c`, results `1a8fe6e81b912313faa32602866556ed6a4049cab47661ded2d6a85066c86ae3`.
  - `20260814T084053828906Z__level_05__benchmark_corpus__level_05_generated_1k_500_prefix_regression_v2__seed42`: manifest `85932a3540a7cfbc7183583cbdced9e3067b7417c688974f8e35cd2178f18354`, results `3b4691c6a21479f037ea8574b24af63211286920a4d731520068a7cce3f4d09e`.

## Lỗi gate

- level_05: deterministic gate failed (83/84)
- level_05: median runtime ratio exceeds 1.8
