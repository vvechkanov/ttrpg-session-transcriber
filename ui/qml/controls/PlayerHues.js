// Per-player hue palette. 6 hand-picked warm colours, same mapping as
// the HTML prototype's PLAYER_HUES. Avatars use `base`; waveforms use
// `base` tinted (done inline in WaveformMock).
//
// Unknown names fall back to the neutral listener hue.

.pragma library

var BY_NAME = {
    Andrey: { base: "#D4843B", soft: "#F7E3C9" },  // GM — accent
    Boris:  { base: "#8A6FB8", soft: "#E6DCF2" },  // muted purple
    Carol:  { base: "#4A8FB5", soft: "#D4E5EF" },  // dusty blue
    Dmitry: { base: "#94897E", soft: "#E5DFD7" },  // neutral (listener)
    Eve:    { base: "#A8683F", soft: "#EBD8C5" },  // terracotta
    Frank:  { base: "#6B8759", soft: "#DBE5CF" }   // sage
};

function forName(name) {
    return BY_NAME[name] || BY_NAME.Dmitry;
}
