# Translation component licenses

The service uses local engines with per-model license tracking. The runtime inventory is generated in `models/models-manifest.json`; it is not committed.

| Component or pack | License | Scope | Evidence |
| --- | --- | --- | --- |
| Argos Translate Python library | MIT | Runtime library only; does not grant rights to language packs or their training data | [License](https://github.com/argosopentech/argos-translate/blob/master/LICENSE) |
| Argos language packs | MIT or CC0 per the upstream maintainer statement; Argos index has no per-pack license field | The inventory records the statement and each package version/source; it is not a per-pack license file | [Maintainer statement](https://github.com/argosopentech/argos-translate/issues/533), [index license](https://github.com/argosopentech/argospm-index/blob/main/LICENSE) |
| M2M-100 418M | MIT | Preserve Meta model and CTranslate2 conversion notices | [Model card](https://huggingface.co/facebook/m2m100_418M) |
| Helsinki-NLP OPUS-MT | Per-model | Downloader checks each card and records revision, license, and attribution. CC-BY models require attribution | [Model cards](https://huggingface.co/Helsinki-NLP) |
| CTranslate2 | MIT | Runtime and conversion tooling | [Documentation](https://opennmt.net/CTranslate2/guides/transformers.html) |
| LibreTranslate / NLLB | Not used | Excluded as requested | — |

Do not infer a model license from the translation runtime license or the package index license. The Argos entries below use the upstream maintainer's blanket MIT-or-CC0 statement because the package index does not identify a license for each pack; confirm the statement still covers each package before redistributing it. OPUS entries are checked against each model card and M2M-100 source/base revisions are recorded.

### Installed Argos packs

Installed from the official Argos package index on 2026-10-16. The index supplied versions and official package URLs, but no per-pack license metadata. The shared license basis is therefore recorded as `MIT or CC0 (upstream maintainer statement)`, not as a separately verified MIT or CC0 license for an individual pack.

| Direction | Version | License basis | Package source |
| --- | --- | --- | --- |
| en→ar | 1.0 | MIT or CC0, upstream statement | [Argos package](https://argos-net.com/v1/translate-en_ar-1_0.argosmodel) |
| ar→en | 1.0 | MIT or CC0, upstream statement | [Argos package](https://argos-net.com/v1/translate-ar_en-1_0.argosmodel) |
| en→es | 1.0 | MIT or CC0, upstream statement | [Argos package](https://argos-net.com/v1/translate-en_es-1_0.argosmodel) |
| es→en | 1.9 | MIT or CC0, upstream statement | [Argos package](https://argos-net.com/v1/translate-es_en-1_9.argosmodel) |
| en→ur | 1.9 | MIT or CC0, upstream statement | [Argos package](https://argos-net.com/v1/translate-en_ur-1_9.argosmodel) |
| ur→en | 1.9 | MIT or CC0, upstream statement | [Argos package](https://argos-net.com/v1/translate-ur_en-1_9.argosmodel) |
| en→zh | 1.9 | MIT or CC0, upstream statement | [Argos package](https://argos-net.com/v1/translate-en_zh-1_9.argosmodel) |
| zh→en | 1.9 | MIT or CC0, upstream statement | [Argos package](https://argos-net.com/v1/translate-zh_en-1_9.argosmodel) |

The active installation inventory is written to `models/argos/translation-licenses.json` and the API model inventory to `models/models-manifest.json`.

The installer requests English in both directions for every configured supported locale. It skips language pairs absent from the index. Cross-language requests pivot through English only when both constituent packs are installed. The currently observed index includes pairs for English↔Urdu, Arabic, Persian, Hindi, Bengali, Simplified and Traditional Chinese, Czech, Dutch, Spanish, French, German, Greek, Hebrew, Hungarian, Indonesian, Italian, Japanese, Korean, Malay, Polish, Portuguese, Romanian, Russian, Swedish, Thai, Turkish, Ukrainian, Vietnamese and Swahili. Shahmukhi Punjabi, Pashto, Sindhi and Tamil have no matching English pair in the checked index and therefore rely on cloud/LLM providers. Recheck the generated inventory after first start.

## Open-source notices

Resora's in-app **Open-source notices** page lists the same engine and model license evidence. Model versions and pair directions shown there should come from the service inventory so the UI reflects exactly what has been installed.
