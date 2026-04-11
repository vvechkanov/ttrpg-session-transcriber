# E2E Fixture: e2e_p2

Synthetic audio fixture for the three-tier regression gate of the
six-layer pipeline refactor (P2.9).

## Files

```
e2e_p2/
├── README.md                    # this file
├── expected_merged.txt          # baseline from new pipeline (regenerate on format changes)
└── session/
    ├── speaker_map.json         # 3-entry map: TestGM, TestPlayer1, TestPlayer2
    ├── 1-test_gm.flac           # ~181 KB Russian TTS, GM turn
    ├── 2-test_player.flac       # ~195 KB Russian TTS, PC turn
    └── 3-test_player2.flac      # ~180 KB Russian TTS, PC turn
```

## Audio fixture details

All FLAC files are 16kHz mono, generated via `scripts/gen_fixtures_noprint.py`.

| File | Speaker stem | Player | Character | Role | Phrase |
|------|-------------|--------|-----------|------|--------|
| 1-test_gm.flac | 1-test_gm | TestGM | (none) | GM | "Хорошо, начинаем игру. Вы находитесь в таверне Золотой дракон..." |
| 2-test_player.flac | 2-test_player | TestPlayer1 | Aragorn | PC | "Мой персонаж осматривает комнату. Есть ли здесь что-нибудь подозрительное..." |
| 3-test_player2.flac | 3-test_player2 | TestPlayer2 | Legolas | PC | "Я подхожу к стойке и прошу у бармена кружку эля..." |

TTS engine: pyttsx3 (Windows SAPI5, offline).
Voice: Microsoft Irina Desktop (Russian).

Note: the baseline uses stem names as speaker labels (1-test_gm, 2-test_player,
3-test_player2) because PipelineParams(speaker_map=None) is used for
deterministic runs. Speaker_map resolution is opt-in; it is tested separately
in test_domain.py.

## Three-tier regression gate

### Tier 1 — Structural (CI-safe, no ASR)

Pure unit tests on domain, mergers, renderers, sources, discovery, pipeline.
No audio, no models, no subprocess.

Run: `pytest tests/ -m "not slow" -v`

### Tier 2 — Semantic (local, requires faster-whisper model)

Runs core.run() on the .flac fixtures and verifies token overlap >= 0.90
vs expected_merged.txt. Tolerates minor ASR drift.

Run: `pytest tests/test_e2e_tier2_semantic.py -v -m slow`

### Tier 3 — Strict diff (manual, one-shot PR validation)

**NOT pytest.** Manual procedure for P2.x PR validation: compare new pipeline
vs legacy on a real session to confirm byte-level or near-byte-level equivalence.

#### Tier 3 procedure

1. Choose a real session directory (e.g., `games/bogomols/` — check `games/`).

2. Run the NEW pipeline:
   ```
   venv\Scripts\python -c "
   import sys; sys.path.insert(0, '.')
   from core.pipeline import PipelineParams, run
   from pathlib import Path
   params = PipelineParams(
       speech_backend='faster-whisper',
       model='bzikst/faster-whisper-large-v3-ru-podlodka',
       device='cpu', compute_type='int8', beam_size=1, language='ru',
       output_filename='merged_new.txt',
   )
   run(Path('games/bogomols/YOUR_SESSION'), params)
   "
   ```

3. Run the LEGACY pipeline on the same session:
   ```
   venv\Scripts\python scripts\wisper_launcher.py games\bogomols\YOUR_SESSION \
     --model large-v3 --device cpu --compute_type int8 --beam_size 1 \
     --language ru --merge --output_dir games\bogomols\YOUR_SESSION
   ```

4. Diff the outputs:
   ```
   diff games/bogomols/YOUR_SESSION/merged.txt games/bogomols/YOUR_SESSION/merged_new.txt
   ```

If byte-match fails due to CTranslate2 non-determinism on CPU, relax to
"same token count ±1%". The purpose is to document the delta for the PR reviewer,
not to gate the merge.

## Regeneration procedure

Run ONLY when deliberately changing the renderer/merger output format.
Document the change in your PR.

### Step 1 — Generate audio fixtures

```bash
cd C:\AI-assistant\Оцифровка_сессии_конспект_из_аудио
venv\Scripts\python scripts\gen_fixtures_noprint.py
```

Requires: `pip install pyttsx3` in venv; ffmpeg at `tools/ffmpeg/bin/ffmpeg.exe`.

### Step 2 — Regenerate baseline using NEW pipeline

```bash
venv\Scripts\python scripts\gen_baseline_newpipeline.py
```

Uses: faster-whisper backend, CPU/int8/beam_size=1 for determinism.
Model: bzikst/faster-whisper-large-v3-ru-podlodka (~3 GB download on first run).
Expected runtime: 5–15 min per track on CPU.

### Step 3 — Review and commit

```bash
git diff tests/fixtures/e2e_p2/expected_merged.txt
git add tests/fixtures/e2e_p2/expected_merged.txt tests/fixtures/e2e_p2/session/*.flac
git commit -m "test(fixtures): regenerate e2e_p2 baseline after <reason>"
```

## Size budget

Total fixture audio: ~557 KB (well under 1 MB git-friendly limit, no LFS needed).

| File | Size |
|------|------|
| 1-test_gm.flac | ~177 KB |
| 2-test_player.flac | ~191 KB |
| 3-test_player2.flac | ~176 KB |
| expected_merged.txt | <5 KB |
| **Total** | **~549 KB** |
