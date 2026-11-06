# Search interface localization

The Search page has a dedicated catalog for 197 interface copy keys covering its primary labels, controls, examples, filters, voice-search controls, and empty states in 36 locales (English plus 35 translated locales). The catalogs are generated with the already installed local M2M-100 model; generation does not download models or call a hosted translation API.

These machine translations need review by fluent speakers before they are treated as publication quality. In particular, M2M-100 Punjabi uses Gurmukhi even though the `pa-Arab` locale is intended for Shahmukhi. Traditional Chinese also uses the model's generic `zh` output and may need script review. The catalog status file records the generation and review state.

Search now exposes a microphone action when the browser supports Web Speech recognition; browsers without it show a localized unavailable state. The voice handler uses the same query-language detection and search stream as typed queries.

The rest of the application uses the broader `i18n/catalogs` catalogs. Those currently cover fewer locales than the Search-only catalogs, so this Search-page guarantee should not be read as a claim that every screen in Resora is fully localized in all 36 languages.

Web results are queried through the backend's Tavily/Exa adapters when configured. Set `TAVILY_API_KEY` or `EXA_API_KEY` in the API environment to enable live web pages; academic search remains available without those credentials.
