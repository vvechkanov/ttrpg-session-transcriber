// Parser type metadata — icon name and accent colour for each
// additional-source parser.
//
// Mirrors the prototype's PARSER_TYPES list. `label` is only used by
// the parser-change menu (step 9 polish); the lane row itself reads
// just `icon` and `color`.

.pragma library

var BY_ID = {
    "foundry-chat": {
        label: "Foundry VTT · чат",
        icon:  "chat",
        color: "#8A6FB8",
        desc:  "Реплики, OOC, системные сообщения"
    },
    "combat-log": {
        label: "Анализатор боя",
        icon:  "swords",
        color: "#C4472B",
        desc:  "Раунды, атаки, урон из файла боя"
    },
    "plain-text": {
        label: "Простой текст",
        icon:  "file",
        color: "#6B8759",
        desc:  "Заметки без разметки — идут как примечания"
    },
    "markdown": {
        label: "Markdown заметки GM",
        icon:  "file",
        color: "#4A8FB5",
        desc:  "# заголовки, списки, ссылки сохраняются"
    }
};

function forId(id) {
    return BY_ID[id] || BY_ID["foundry-chat"];
}

function shortLabel(id) {
    // "Foundry VTT · чат" → "Foundry VTT"
    return forId(id).label.split("·")[0].trim();
}
