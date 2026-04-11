import { useState } from 'react';
import { UserPlus, FileAudio, ChevronRight, ChevronDown, AlertTriangle } from 'lucide-react';
import { HelpTooltip } from './HelpTooltip';

interface Speaker {
  file: string;
  player: string;
  role: 'GM' | 'Игрок' | 'Слушатель';
  character: string;
  isNew?: boolean;
  isEdited?: boolean;
}

interface AudioGigaamSettingsPanelProps {
  onDirtyChange?: (isDirty: boolean) => void;
  variant?: 'clean' | 'new-speakers' | 'dirty';
}

export function AudioGigaamSettingsPanel({ onDirtyChange, variant = 'clean' }: AudioGigaamSettingsPanelProps) {
  const [showNewSpeakersBanner] = useState(variant === 'new-speakers');
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const initialSpeakers: Speaker[] = variant === 'clean'
    ? [
        { file: '1-Andrey.flac', player: 'Andrey', role: 'GM', character: 'Гендальф' },
        { file: '2-Boris.flac', player: 'Boris', role: 'Игрок', character: 'Арагорн' },
        { file: '3-Carol.flac', player: 'Carol', role: 'Игрок', character: 'Лютиэн' },
        { file: '4-Dmitry.flac', player: 'Dmitry', role: 'Игрок', character: 'Леголас' },
        { file: '5-Eve.flac', player: 'Eve', role: 'Игрок', character: 'Галадриэль' },
        { file: '6-Frank.flac', player: 'Frank', role: 'Игрок', character: 'Боромир' },
      ]
    : [
        { file: '1-Andrey.flac', player: 'Andrey', role: 'GM', character: 'Гендальф' },
        { file: '2-Boris.flac', player: 'Boris', role: 'Игрок', character: 'Арагорн' },
        { file: '3-Carol.flac', player: '', role: 'Игрок', character: '', isNew: true },
        { file: '4-Dmitry.flac', player: '', role: 'Игрок', character: '', isNew: true },
        { file: '5-Eve.flac', player: '', role: 'Игрок', character: '', isNew: true },
        { file: '6-Frank.flac', player: '', role: 'Игрок', character: '', isNew: true },
      ];

  const [speakers, setSpeakers] = useState<Speaker[]>(initialSpeakers);
  const [hotwords, setHotwords] = useState(
    variant === 'dirty'
      ? 'Гендальф\nАрагорн\nЛютиэн\nГаладриэль\nБоромир\nМория\nПалантир\nРивенделл'
      : 'Гендальф\nАрагорн\nЛютиэн\nГаладриэль\nБоромир\nМория\nПалантир'
  );
  const [computePrecision, setComputePrecision] = useState<'fp32' | 'int8'>('fp32');
  const [vadSensitivity, setVadSensitivity] = useState(0.50);
  const [minPause, setMinPause] = useState(500);
  const [maxSegment, setMaxSegment] = useState(15);

  const files = [
    { name: '1-Andrey.flac', duration: '3:47:12', size: '142 MB' },
    { name: '2-Boris.flac', duration: '3:47:08', size: '138 MB' },
    { name: '3-Carol.flac', duration: '3:47:15', size: '145 MB' },
    { name: '4-Dmitry.flac', duration: '3:47:10', size: '140 MB' },
    { name: '5-Eve.flac', duration: '3:47:13', size: '143 MB' },
    { name: '6-Frank.flac', duration: '3:47:11', size: '141 MB' },
  ];

  const hotwordsCount = hotwords.split('\n').filter(w => w.trim()).length;

  const updateSpeaker = (index: number, field: keyof Speaker, value: string) => {
    setSpeakers(prev => prev.map((s, i) =>
      i === index ? { ...s, [field]: value, isEdited: true } : s
    ));
    onDirtyChange?.(true);
  };

  const scrollToSpeakers = () => {
    document.getElementById('speakers-section')?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="space-y-8">
      {/* Section 1: New speakers banner */}
      {showNewSpeakersBanner && (
        <div className="bg-accent/8 border border-accent/20 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <UserPlus size={20} className="text-accent mt-0.5" />
            <div className="flex-1">
              <p className="font-medium mb-1">Найдено 4 новых участника</p>
              <p className="text-sm text-muted-foreground">
                Назначьте им роли в таблице ниже, прежде чем запускать обработку
              </p>
            </div>
            <button
              onClick={scrollToSpeakers}
              className="text-sm text-accent hover:text-accent/80 transition-colors whitespace-nowrap"
            >
              перейти →
            </button>
          </div>
        </div>
      )}

      {/* Section 2: Input files */}
      <div>
        <h3 className="text-xs tracking-wide text-muted-foreground uppercase mb-1">
          Входные файлы
        </h3>
        <p className="text-xs text-muted-foreground mb-4">
          Файлы из CraigZip, распакованные автоматически
        </p>

        <div className="space-y-2 mb-3">
          {files.map((file) => (
            <div key={file.name} className="flex items-center gap-3 py-2">
              <FileAudio size={16} className="text-muted-foreground" />
              <span className="font-mono text-sm flex-1">{file.name}</span>
              <span className="text-xs text-muted-foreground">
                {file.duration} · {file.size}
              </span>
            </div>
          ))}
        </div>

        <div className="flex justify-end">
          <button className="text-sm text-muted-foreground hover:text-foreground transition-colors">
            Заменить CraigZip →
          </button>
        </div>
      </div>

      {/* Section 3: Speakers & roles */}
      <div id="speakers-section">
        <h3 className="text-xs tracking-wide text-muted-foreground uppercase mb-1">
          Участники и роли
        </h3>
        <p className="text-xs text-muted-foreground mb-4">
          Какая дорожка чей голос. Роль «Слушатель» исключает дорожку из обработки
        </p>

        <div className="space-y-3">
          {speakers.map((speaker, index) => (
            <div
              key={speaker.file}
              className={`flex items-center gap-3 p-3 rounded-lg border transition-colors ${
                speaker.isNew
                  ? 'border-l-2 border-l-accent bg-accent/5'
                  : 'border-border'
              }`}
            >
              {speaker.isEdited && !speaker.isNew && (
                <div className="w-1.5 h-1.5 rounded-full bg-accent flex-shrink-0" />
              )}
              {speaker.isNew && (
                <div className="w-1.5 h-1.5 rounded-full bg-accent flex-shrink-0" />
              )}

              <div className="flex items-center gap-3 flex-1">
                <div className="w-32">
                  <span className="font-mono text-sm text-muted-foreground">
                    {speaker.file}
                  </span>
                </div>

                <input
                  type="text"
                  value={speaker.player}
                  onChange={(e) => updateSpeaker(index, 'player', e.target.value)}
                  placeholder="имя игрока"
                  className="flex-1 px-3 py-1.5 text-sm bg-input-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/50"
                />

                <div className="flex gap-1 bg-secondary rounded-lg p-1">
                  {(['GM', 'Игрок', 'Слушатель'] as const).map((role) => (
                    <button
                      key={role}
                      onClick={() => updateSpeaker(index, 'role', role)}
                      className={`px-3 py-1 text-xs rounded transition-colors ${
                        speaker.role === role
                          ? 'bg-card text-foreground shadow-sm'
                          : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      {role}
                    </button>
                  ))}
                </div>

                <input
                  type="text"
                  value={speaker.character}
                  onChange={(e) => updateSpeaker(index, 'character', e.target.value)}
                  placeholder="имя персонажа"
                  className="flex-1 px-3 py-1.5 text-sm bg-input-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/50"
                />
              </div>
            </div>
          ))}
        </div>

        <button className="mt-3 text-sm text-muted-foreground hover:text-foreground transition-colors">
          + добавить участника вручную
        </button>
      </div>

      {/* Section 4: Engine */}
      <div>
        <h3 className="text-xs tracking-wide text-muted-foreground uppercase mb-4">
          Движок
        </h3>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <label className="text-sm">Backend</label>
              <HelpTooltip content="GigaAM-v3 RNNT — российская модель распознавания речи, оптимизированная для русского языка. Обеспечивает высокую точность даже при наличии акцентов и шумов." />
            </div>
            <div className="px-3 py-1.5 bg-muted/50 text-sm text-muted-foreground rounded-lg border border-border">
              GigaAM-v3 RNNT
            </div>
          </div>

          <div className="flex items-center justify-between">
            <label className="text-sm">Язык</label>
            <div className="px-3 py-1.5 bg-muted/50 text-sm text-muted-foreground rounded-lg border border-border">
              Русский
            </div>
          </div>

          <div>
            <div className="flex items-center gap-2 mb-3">
              <label className="text-sm">Точность вычислений</label>
              <HelpTooltip content="Как числа хранятся в памяти модели. fp32 — эталон, максимальное качество. int8 — оптимизация, быстрее работает, немного менее точно." />
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => {
                  setComputePrecision('fp32');
                  onDirtyChange?.(true);
                }}
                className={`flex-1 p-3 rounded-lg border transition-colors text-left ${
                  computePrecision === 'fp32'
                    ? 'border-accent bg-accent/5'
                    : 'border-border hover:border-accent/50'
                }`}
              >
                <div className="font-medium text-sm mb-1">fp32</div>
                <div className="text-xs text-muted-foreground">максимальное качество, медленнее</div>
              </button>

              <button
                onClick={() => {
                  setComputePrecision('int8');
                  onDirtyChange?.(true);
                }}
                className={`flex-1 p-3 rounded-lg border transition-colors text-left ${
                  computePrecision === 'int8'
                    ? 'border-accent bg-accent/5'
                    : 'border-border hover:border-accent/50'
                }`}
              >
                <div className="font-medium text-sm mb-1">int8</div>
                <div className="text-xs text-muted-foreground">быстрее, немного менее точно</div>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Section 5: Hotwords */}
      <div>
        <h3 className="text-xs tracking-wide text-muted-foreground uppercase mb-1">
          Горячие слова
        </h3>
        <p className="text-xs text-muted-foreground mb-4">
          Имена персонажей, локаций, заклинаний — по одному на строку. Помогает распознавать редкие слова
        </p>

        <textarea
          value={hotwords}
          onChange={(e) => {
            setHotwords(e.target.value);
            onDirtyChange?.(true);
          }}
          className="w-full h-48 px-3 py-2 text-sm font-mono bg-input-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent/50 resize-none"
          placeholder="Введите слова по одному на строку..."
        />

        <p className="text-xs text-muted-foreground mt-2">{hotwordsCount} слов</p>
      </div>

      {/* Section 6: Advanced */}
      <div>
        <button
          onClick={() => setAdvancedOpen(!advancedOpen)}
          className="flex items-center justify-between w-full text-left group"
        >
          <div>
            <h3 className="text-xs tracking-wide text-muted-foreground uppercase">
              Продвинутые
            </h3>
            <p className="text-xs text-muted-foreground">Тонкая настройка VAD и сегментации</p>
          </div>
          {advancedOpen ? (
            <ChevronDown size={20} className="text-muted-foreground group-hover:text-foreground transition-colors" />
          ) : (
            <ChevronRight size={20} className="text-muted-foreground group-hover:text-foreground transition-colors" />
          )}
        </button>

        {advancedOpen && (
          <div className="mt-4 space-y-6 pt-4 border-t border-border">
            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <label className="text-sm">Чувствительность речевой активности</label>
                  <HelpTooltip content="VAD (Voice Activity Detection) — определение, где речь, а где тишина. Выше значение = строже фильтрация, меньше ложных срабатываний." />
                </div>
                <span className="text-sm font-mono text-muted-foreground">{vadSensitivity.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min="0.30"
                max="0.70"
                step="0.05"
                value={vadSensitivity}
                onChange={(e) => {
                  setVadSensitivity(parseFloat(e.target.value));
                  onDirtyChange?.(true);
                }}
                className="w-full"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-3">
                <label className="text-sm">Минимальная пауза (мс)</label>
                <span className="text-sm font-mono text-muted-foreground">{minPause}</span>
              </div>
              <input
                type="range"
                min="100"
                max="2000"
                step="100"
                value={minPause}
                onChange={(e) => {
                  setMinPause(parseInt(e.target.value));
                  onDirtyChange?.(true);
                }}
                className="w-full"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-3">
                <label className="text-sm">Макс. длина сегмента (сек)</label>
                <span className="text-sm font-mono text-muted-foreground">{maxSegment}</span>
              </div>
              <input
                type="range"
                min="5"
                max="30"
                step="5"
                value={maxSegment}
                onChange={(e) => {
                  setMaxSegment(parseInt(e.target.value));
                  onDirtyChange?.(true);
                }}
                className="w-full"
              />
            </div>

            <div className="bg-muted/30 border border-border rounded-lg p-3 flex items-start gap-3">
              <AlertTriangle size={16} className="text-muted-foreground mt-0.5 flex-shrink-0" />
              <p className="text-xs text-muted-foreground">
                Меняйте только если знаете, что делаете. По умолчанию всё работает.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
