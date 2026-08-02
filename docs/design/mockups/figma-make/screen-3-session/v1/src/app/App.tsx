import { useState } from 'react';
import { ChevronRight, AudioWaveform, MessageSquare, Play, Clock, Check, Loader2, FileText, Plus } from 'lucide-react';
import { HelpTooltip } from './components/HelpTooltip';
import { SidePanel } from './components/SidePanel';
import { ConfirmDialog } from './components/ConfirmDialog';
import { AudioGigaamSettingsPanel } from './components/AudioGigaamSettingsPanel';
import { FasterWhisperSettingsPanel } from './components/FasterWhisperSettingsPanel';

type ViewState = 'idle' | 'running' | 'done';
type PanelType = 'audio-settings' | 'chat-settings' | 'merger-settings' | 'output-settings' | 'add-source' | null;
type AudioSettingsVariant = 'clean' | 'new-speakers' | 'dirty';
type WhisperSettingsVariant = 'default' | 'new-speakers-custom' | 'advanced-open';
type AudioBackend = 'gigaam' | 'whisper';

export default function App() {
  const [state, setState] = useState<ViewState>('idle');
  const [openPanel, setOpenPanel] = useState<PanelType>(null);
  const [showClearCacheDialog, setShowClearCacheDialog] = useState(false);
  const [audioBackend, setAudioBackend] = useState<AudioBackend>('gigaam');
  const [audioSettingsVariant, setAudioSettingsVariant] = useState<AudioSettingsVariant>('clean');
  const [whisperSettingsVariant, setWhisperSettingsVariant] = useState<WhisperSettingsVariant>('default');
  const [isAudioSettingsDirty, setIsAudioSettingsDirty] = useState(false);

  return (
    <div className="min-h-screen bg-background">
      {/* State switcher for demo */}
      <div className="fixed top-4 right-4 flex flex-col gap-2 z-50">
        <div className="flex gap-2 bg-card p-1 rounded-lg shadow-lg">
          <button
            onClick={() => setState('idle')}
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
              state === 'idle' ? 'bg-accent text-accent-foreground' : 'text-foreground hover:bg-secondary'
            }`}
          >
            Idle
          </button>
          <button
            onClick={() => setState('running')}
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
              state === 'running' ? 'bg-accent text-accent-foreground' : 'text-foreground hover:bg-secondary'
            }`}
          >
            Running
          </button>
          <button
            onClick={() => setState('done')}
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
              state === 'done' ? 'bg-accent text-accent-foreground' : 'text-foreground hover:bg-secondary'
            }`}
          >
            Done
          </button>
        </div>

        <div className="bg-card p-2 rounded-lg shadow-lg space-y-2">
          <div className="flex gap-2">
            <button
              onClick={() => {
                setAudioBackend('gigaam');
                setIsAudioSettingsDirty(false);
              }}
              className={`flex-1 px-3 py-1.5 text-xs rounded-lg transition-colors ${
                audioBackend === 'gigaam' ? 'bg-accent text-accent-foreground' : 'text-foreground hover:bg-secondary'
              }`}
            >
              GigaAM
            </button>
            <button
              onClick={() => {
                setAudioBackend('whisper');
                setIsAudioSettingsDirty(false);
              }}
              className={`flex-1 px-3 py-1.5 text-xs rounded-lg transition-colors ${
                audioBackend === 'whisper' ? 'bg-accent text-accent-foreground' : 'text-foreground hover:bg-secondary'
              }`}
            >
              Whisper
            </button>
          </div>

          {audioBackend === 'gigaam' && (
            <div className="flex gap-2 pt-2 border-t border-border">
              <button
                onClick={() => {
                  setAudioSettingsVariant('clean');
                  setIsAudioSettingsDirty(false);
                }}
                className={`flex-1 px-2 py-1 text-xs rounded transition-colors ${
                  audioSettingsVariant === 'clean' ? 'bg-accent text-accent-foreground' : 'text-foreground hover:bg-secondary'
                }`}
              >
                Clean
              </button>
              <button
                onClick={() => {
                  setAudioSettingsVariant('new-speakers');
                  setIsAudioSettingsDirty(false);
                }}
                className={`flex-1 px-2 py-1 text-xs rounded transition-colors ${
                  audioSettingsVariant === 'new-speakers' ? 'bg-accent text-accent-foreground' : 'text-foreground hover:bg-secondary'
                }`}
              >
                New
              </button>
              <button
                onClick={() => {
                  setAudioSettingsVariant('dirty');
                  setIsAudioSettingsDirty(true);
                }}
                className={`flex-1 px-2 py-1 text-xs rounded transition-colors ${
                  audioSettingsVariant === 'dirty' ? 'bg-accent text-accent-foreground' : 'text-foreground hover:bg-secondary'
                }`}
              >
                Dirty
              </button>
            </div>
          )}

          {audioBackend === 'whisper' && (
            <div className="flex gap-2 pt-2 border-t border-border">
              <button
                onClick={() => {
                  setWhisperSettingsVariant('default');
                  setIsAudioSettingsDirty(false);
                }}
                className={`flex-1 px-2 py-1 text-xs rounded transition-colors ${
                  whisperSettingsVariant === 'default' ? 'bg-accent text-accent-foreground' : 'text-foreground hover:bg-secondary'
                }`}
              >
                Default
              </button>
              <button
                onClick={() => {
                  setWhisperSettingsVariant('new-speakers-custom');
                  setIsAudioSettingsDirty(true);
                }}
                className={`flex-1 px-2 py-1 text-xs rounded transition-colors ${
                  whisperSettingsVariant === 'new-speakers-custom' ? 'bg-accent text-accent-foreground' : 'text-foreground hover:bg-secondary'
                }`}
              >
                Custom
              </button>
              <button
                onClick={() => {
                  setWhisperSettingsVariant('advanced-open');
                  setIsAudioSettingsDirty(false);
                }}
                className={`flex-1 px-2 py-1 text-xs rounded transition-colors ${
                  whisperSettingsVariant === 'advanced-open' ? 'bg-accent text-accent-foreground' : 'text-foreground hover:bg-secondary'
                }`}
              >
                Advanced
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Main content */}
      <div className="px-8 py-6">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-6">
          <span className="text-foreground">Storm King&apos;s Thunder</span>
          <ChevronRight size={16} />
          <span>Сессия 14 — Битва на мосту</span>
        </div>

        {/* Tabs */}
        <div className="flex gap-8 border-b border-border mb-8">
          <button className="pb-3 text-sm border-b-2 border-accent text-foreground">
            Обработка
          </button>
          <button className="pb-3 text-sm text-muted-foreground hover:text-foreground transition-colors">
            Транскрипт
          </button>
          <button className="pb-3 text-sm text-muted-foreground hover:text-foreground transition-colors">
            Журнал
          </button>
          <button className="pb-3 text-sm text-muted-foreground hover:text-foreground transition-colors">
            Настройки сессии
          </button>
        </div>

        {/* Pipeline blocks */}
        <div className="max-w-[1200px] space-y-5">
          {/* Block 1: Sources */}
          <div className="bg-card rounded-xl p-6 shadow-[0_2px_8px_rgba(107,98,90,0.08)]">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-xs tracking-wide text-muted-foreground uppercase">Источники</h3>
              {state === 'idle' && (
                <button
                  onClick={() => setOpenPanel('add-source')}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-foreground hover:bg-secondary rounded-lg transition-colors"
                >
                  <span className="text-lg leading-none">+</span>
                  <span>добавить источник</span>
                </button>
              )}
            </div>

            <div className="flex gap-4">
              {/* Audio source card */}
              <div className={`flex-1 bg-card border rounded-xl p-5 transition-all ${
                state === 'running' ? 'border-accent shadow-[0_0_0_2px_rgba(212,132,59,0.15)]' : 'border-border'
              } ${state === 'running' ? 'opacity-100' : state === 'done' ? 'opacity-100' : 'opacity-100'}`}>
                <div className="flex items-center gap-2 mb-2">
                  <AudioWaveform size={18} className="text-accent" />
                  <h4 className="text-base">Аудио</h4>
                  <div className="ml-auto">
                    <HelpTooltip content="GigaAM-v3 RNNT — это современная нейронная модель для распознавания русской речи, разработанная компанией GigaAM. Модель использует архитектуру RNNT (Recurrent Neural Network Transducer) и обеспечивает высокую точность распознавания даже при наличии шумов и акцентов. Основные преимущества: точность распознавания до 95%, поддержка длинных аудиозаписей, низкая задержка обработки." />
                  </div>
                </div>
                <p className="text-xs text-muted-foreground mb-4">GigaAM-v3 RNNT · русский</p>

                <div className="space-y-1 mb-4 text-sm text-foreground font-mono">
                  <div className="flex items-center gap-2">
                    <FileText size={14} className="text-muted-foreground" />
                    <span>1-Andrey.flac</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <FileText size={14} className="text-muted-foreground" />
                    <span>2-Boris.flac</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <FileText size={14} className="text-muted-foreground" />
                    <span>3-Carol.flac</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <FileText size={14} className="text-muted-foreground" />
                    <span>4-Dmitry.flac</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <FileText size={14} className="text-muted-foreground" />
                    <span>5-Eve.flac</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <FileText size={14} className="text-muted-foreground" />
                    <span>6-Frank.flac</span>
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-lg ${
                    state === 'running' ? 'bg-accent/10 text-accent' :
                    state === 'done' ? 'bg-success/10 text-success' :
                    'bg-success/10 text-success'
                  }`}>
                    {state === 'running' && <Loader2 size={12} className="animate-spin" />}
                    {state === 'done' && <Check size={12} />}
                    {state === 'idle' && <Check size={12} />}
                    {state === 'running' ? 'в работе' : 'готов'}
                  </span>
                  <button
                    disabled={state === 'running'}
                    onClick={() => setOpenPanel('audio-settings')}
                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                      state === 'running'
                        ? 'text-muted-foreground cursor-not-allowed'
                        : 'text-foreground hover:bg-secondary'
                    }`}
                  >
                    Настроить
                  </button>
                </div>
              </div>

              {/* Foundry chat source card */}
              <div className={`flex-1 bg-card border border-border rounded-xl p-5 transition-opacity ${
                state === 'running' ? 'opacity-50' : 'opacity-100'
              }`}>
                <div className="flex items-center gap-2 mb-2">
                  <MessageSquare size={18} className="text-accent" />
                  <h4 className="text-base">Foundry VTT чат</h4>
                  <div className="ml-auto">
                    <HelpTooltip content="Foundry Virtual Tabletop — это платформа для проведения настольных ролевых игр онлайн. Парсер извлекает сообщения из чат-лога Foundry и синхронизирует их с аудиозаписями по временным меткам. Это позволяет создать полный транскрипт игровой сессии, включая как голосовое общение, так и текстовые сообщения, броски кубиков и системные события." />
                  </div>
                </div>
                <p className="text-xs text-muted-foreground mb-4">&nbsp;</p>

                <div className="mb-4">
                  <div className="flex items-center gap-2 mb-1 text-sm text-foreground font-mono">
                    <FileText size={14} className="text-muted-foreground" />
                    <span>chat-log-2026-04-10.db</span>
                  </div>
                  <p className="text-xs text-muted-foreground ml-6">1423 реплики · 12 участников</p>
                </div>

                <div className="flex items-center justify-between">
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-lg ${
                    state === 'done' ? 'bg-success/10 text-success' : 'bg-success/10 text-success'
                  }`}>
                    <Check size={12} />
                    готов
                  </span>
                  <button
                    disabled={state === 'running'}
                    onClick={() => setOpenPanel('chat-settings')}
                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                      state === 'running'
                        ? 'text-muted-foreground cursor-not-allowed'
                        : 'text-foreground hover:bg-secondary'
                    }`}
                  >
                    Настроить
                  </button>
                </div>
              </div>

              {/* Add source tile */}
              {state === 'idle' && (
                <div className="flex-1 border-2 border-dashed border-border rounded-xl p-5 flex flex-col items-center justify-center text-center">
                  <div className="w-12 h-12 rounded-full bg-secondary flex items-center justify-center mb-3">
                    <span className="text-2xl text-muted-foreground">+</span>
                  </div>
                  <p className="text-sm text-foreground mb-1">Добавить источник</p>
                  <p className="text-xs text-muted-foreground">Аудио, чат, или другой парсер</p>
                </div>
              )}
            </div>
          </div>

          {/* Block 2: Merger */}
          <div className={`bg-card rounded-xl p-5 shadow-[0_2px_8px_rgba(107,98,90,0.08)] transition-opacity ${
            state === 'running' ? 'opacity-50' : 'opacity-100'
          }`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Clock size={18} className="text-accent" />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-base">Мержер: timeline-v1</span>
                    {state === 'done' && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-success/10 text-success rounded">
                        <Check size={12} />
                      </span>
                    )}
                    <HelpTooltip content="Алгоритм timeline-v1 объединяет события из разных источников (аудио, чат, системные логи) на единой временной шкале. Каждое событие имеет точную временную метку, что позволяет восстановить хронологию игровой сессии. Мержер автоматически синхронизирует аудиотреки с текстовыми сообщениями и системными событиями, создавая единый связный транскрипт." />
                  </div>
                  <p className="text-xs text-muted-foreground">Объединение событий по временным меткам</p>
                </div>
              </div>
              <button
                disabled={state === 'running'}
                onClick={() => setOpenPanel('merger-settings')}
                className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                  state === 'running'
                    ? 'text-muted-foreground cursor-not-allowed'
                    : 'text-foreground hover:bg-secondary'
                }`}
              >
                Настроить
              </button>
            </div>
          </div>

          {/* Block 3: Processing */}
          <div className="bg-card rounded-xl p-6 shadow-[0_2px_8px_rgba(107,98,90,0.08)] min-h-[420px] flex flex-col">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xs tracking-wide text-muted-foreground uppercase">Обработка</h3>
              {state === 'idle' && (
                <button className="flex items-center gap-2 px-6 py-3 bg-accent text-accent-foreground rounded-xl hover:bg-accent/90 transition-colors">
                  <Play size={20} />
                  <span>Запустить обработку</span>
                </button>
              )}
              {state === 'done' && (
                <button className="flex items-center gap-2 px-6 py-3 bg-accent text-accent-foreground rounded-xl hover:bg-accent/90 transition-colors">
                  <Play size={20} />
                  <span>Перезапустить</span>
                </button>
              )}
            </div>

            {/* Idle state */}
            {state === 'idle' && (
              <div className="flex-1 flex flex-col items-center justify-center text-center">
                <div className="w-16 h-16 rounded-full bg-accent/10 flex items-center justify-center mb-4">
                  <Play size={32} className="text-accent/40" />
                </div>
                <p className="text-base text-foreground mb-2">Нажмите «Запустить», чтобы начать</p>
                <p className="text-sm text-muted-foreground">Прогресс каждого источника появится здесь</p>
              </div>
            )}

            {/* Running state */}
            {state === 'running' && (
              <div className="flex-1 flex flex-col">
                <div className="mb-4">
                  <div className="flex items-center gap-2 mb-1">
                    <AudioWaveform size={18} className="text-accent" />
                    <h4 className="text-base">Аудио · GigaAM-v3</h4>
                  </div>
                  <div className="h-px bg-border my-3"></div>
                </div>

                <div className="space-y-3 flex-1">
                  {/* Track progress rows */}
                  <div className="flex items-center gap-4">
                    <span className="text-sm w-20">Andrey</span>
                    <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden">
                      <div className="h-full bg-accent rounded-full" style={{ width: '67%' }}></div>
                    </div>
                    <span className="text-sm text-muted-foreground w-16 text-right">67%</span>
                    <span className="text-sm text-muted-foreground w-20 text-right">2 мин</span>
                    <span className="text-xs px-2 py-0.5 bg-accent/10 text-accent rounded">GM</span>
                    <span className="text-sm text-muted-foreground">Гендальф</span>
                  </div>

                  <div className="flex items-center gap-4">
                    <span className="text-sm w-20">Boris</span>
                    <div className="flex-1 h-2 bg-success/20 rounded-full overflow-hidden">
                      <div className="h-full bg-success rounded-full" style={{ width: '100%' }}></div>
                    </div>
                    <span className="text-sm text-success w-16 text-right flex items-center gap-1">
                      <Check size={14} />
                      кэш
                    </span>
                    <span className="text-sm text-muted-foreground w-20 text-right"></span>
                    <span className="text-xs px-2 py-0.5 bg-muted text-foreground rounded">Игрок</span>
                    <span className="text-sm text-muted-foreground">Арагорн</span>
                  </div>

                  <div className="flex items-center gap-4">
                    <span className="text-sm w-20">Carol</span>
                    <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden">
                      <div className="h-full bg-muted rounded-full" style={{ width: '0%' }}></div>
                    </div>
                    <span className="text-sm text-muted-foreground w-16 text-right">в очереди</span>
                    <span className="text-sm text-muted-foreground w-20 text-right"></span>
                    <span className="text-xs px-2 py-0.5 bg-muted text-foreground rounded">Игрок</span>
                    <span className="text-sm text-muted-foreground">Лютиэн</span>
                  </div>

                  <div className="flex items-center gap-4 opacity-60">
                    <span className="text-sm w-20">Dmitry</span>
                    <div className="flex-1"></div>
                    <span className="text-sm text-muted-foreground col-span-3">исключён (роль «слушатель»)</span>
                  </div>

                  <div className="flex items-center gap-4">
                    <span className="text-sm w-20">Eve</span>
                    <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden">
                      <div className="h-full bg-muted rounded-full" style={{ width: '0%' }}></div>
                    </div>
                    <span className="text-sm text-muted-foreground w-16 text-right">в очереди</span>
                    <span className="text-sm text-muted-foreground w-20 text-right"></span>
                    <span className="text-xs px-2 py-0.5 bg-muted text-foreground rounded">Игрок</span>
                    <span className="text-sm text-muted-foreground">Галадриэль</span>
                  </div>

                  <div className="flex items-center gap-4">
                    <span className="text-sm w-20">Frank</span>
                    <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden">
                      <div className="h-full bg-muted rounded-full" style={{ width: '0%' }}></div>
                    </div>
                    <span className="text-sm text-muted-foreground w-16 text-right">в очереди</span>
                    <span className="text-sm text-muted-foreground w-20 text-right"></span>
                    <span className="text-xs px-2 py-0.5 bg-muted text-foreground rounded">Игрок</span>
                    <span className="text-sm text-muted-foreground">Боромир</span>
                  </div>
                </div>

                <div className="mt-6 pt-4 border-t border-border">
                  <p className="text-sm text-muted-foreground">
                    Текущий этап: VAD + ASR дорожки Andrey. Кэш: 1 из 5 дорожек.
                  </p>
                </div>

                {/* Overall progress indicator */}
                <div className="mt-4 flex items-center justify-center gap-3 py-3 bg-secondary/50 rounded-xl">
                  <Loader2 size={20} className="text-accent animate-spin" />
                  <span className="text-base">42% · ~11 минут осталось</span>
                </div>
              </div>
            )}

            {/* Done state */}
            {state === 'done' && (
              <div className="flex-1 flex flex-col">
                <div className="flex items-center gap-3 mb-6">
                  <div className="w-12 h-12 rounded-full bg-success/10 flex items-center justify-center">
                    <Check size={24} className="text-success" />
                  </div>
                  <h4 className="text-xl">Готово за 14 минут 23 секунды</h4>
                </div>

                <div className="space-y-3 flex-1">
                  <div className="flex items-start gap-3">
                    <span className="text-muted-foreground mt-1">•</span>
                    <p className="text-sm">
                      <span className="text-foreground">Аудио · GigaAM-v3:</span>
                      <span className="text-muted-foreground"> 5 дорожек, 3ч 47м, 12 340 событий</span>
                    </p>
                  </div>
                  <div className="flex items-start gap-3">
                    <span className="text-muted-foreground mt-1">•</span>
                    <p className="text-sm">
                      <span className="text-foreground">Foundry VTT чат:</span>
                      <span className="text-muted-foreground"> 1 423 события</span>
                    </p>
                  </div>
                  <div className="flex items-start gap-3">
                    <span className="text-muted-foreground mt-1">•</span>
                    <p className="text-sm">
                      <span className="text-foreground">Мержер timeline-v1:</span>
                      <span className="text-muted-foreground"> 13 763 события в итоговом таймлайне</span>
                    </p>
                  </div>
                  <div className="flex items-start gap-3">
                    <span className="text-muted-foreground mt-1">•</span>
                    <p className="text-sm">
                      <span className="text-foreground">Рендерер:</span>
                      <span className="text-muted-foreground"> merged.txt (84 KB)</span>
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Footer */}
            <div className="mt-6 pt-4 border-t border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="use-cache"
                  className="w-4 h-4 rounded border-border"
                  defaultChecked
                  disabled={state === 'running'}
                />
                <label
                  htmlFor="use-cache"
                  className={`text-sm ${state === 'running' ? 'text-muted-foreground cursor-not-allowed' : 'text-foreground cursor-pointer'}`}
                >
                  использовать кэши
                </label>
                <HelpTooltip content="Кэширование позволяет избежать повторной обработки уже распознанных аудиодорожек. Если файл не изменился с момента последней обработки, результаты будут взяты из кэша, что значительно ускоряет процесс. Кэши хранятся локально в папке проекта и могут быть очищены в любой момент." />
              </div>
              <button
                disabled={state === 'running'}
                onClick={() => setShowClearCacheDialog(true)}
                className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                  state === 'running'
                    ? 'text-muted-foreground cursor-not-allowed'
                    : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
                }`}
              >
                очистить кэш сессии
              </button>
            </div>
          </div>

          {/* Block 4: Output */}
          <div className={`bg-card rounded-xl p-6 shadow-[0_2px_8px_rgba(107,98,90,0.08)] transition-opacity ${
            state === 'running' ? 'opacity-50' : 'opacity-100'
          }`}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs tracking-wide text-muted-foreground uppercase">Вывод</h3>
              <button
                disabled={state === 'running'}
                onClick={() => setOpenPanel('output-settings')}
                className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                  state === 'running'
                    ? 'text-muted-foreground cursor-not-allowed'
                    : 'text-foreground hover:bg-secondary'
                }`}
              >
                Настроить
              </button>
            </div>

            <div className="flex items-center gap-3 mb-3">
              <FileText size={18} className="text-accent" />
              <div className="flex-1">
                <p className="text-base text-foreground font-mono">merged.txt</p>
                <p className="text-xs text-muted-foreground">Формат: единый текст с таймкодами</p>
              </div>
              <HelpTooltip content="Рендерер преобразует события из таймлайна в финальный текстовый файл. Формат вывода определяет структуру итогового транскрипта: можно выбрать простой текст с таймкодами, Markdown с форматированием, JSON для дальнейшей обработки или HTML для просмотра в браузере. Имя файла и путь сохранения настраиваются отдельно." />
            </div>

            {state === 'done' ? (
              <div className="flex items-center gap-3 mt-4">
                <div className="flex-1">
                  <p className="text-sm text-muted-foreground">84 KB · 12 473 слова</p>
                </div>
                <button className="px-4 py-2 bg-accent text-accent-foreground rounded-lg hover:bg-accent/90 transition-colors">
                  Открыть
                </button>
                <button className="px-4 py-2 text-foreground hover:bg-secondary rounded-lg transition-colors">
                  Показать в папке
                </button>
              </div>
            ) : (
              <div className="mt-4">
                <p className="text-sm text-muted-foreground">Файл появится после обработки</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Side Panels */}
      <SidePanel
        isOpen={openPanel === 'audio-settings'}
        onClose={() => {
          setOpenPanel(null);
          setIsAudioSettingsDirty(false);
        }}
        title="Настройки · Аудио"
        subtitle={
          audioBackend === 'gigaam'
            ? 'GigaAM-v3 RNNT · русский'
            : 'faster-whisper · large-v3 · многоязычная'
        }
        icon="audio"
        showFooter={true}
        isDirty={isAudioSettingsDirty}
        onSave={() => {
          console.log('Audio settings saved');
          setIsAudioSettingsDirty(false);
          setOpenPanel(null);
        }}
      >
        {audioBackend === 'gigaam' ? (
          <AudioGigaamSettingsPanel
            variant={audioSettingsVariant}
            onDirtyChange={setIsAudioSettingsDirty}
          />
        ) : (
          <FasterWhisperSettingsPanel
            variant={whisperSettingsVariant}
            onDirtyChange={setIsAudioSettingsDirty}
          />
        )}
      </SidePanel>

      <SidePanel
        isOpen={openPanel === 'chat-settings'}
        onClose={() => setOpenPanel(null)}
        title="Настройки Foundry VTT чат"
      >
        <div className="space-y-6">
          <p className="text-sm text-muted-foreground">
            Настройки парсера чата Foundry VTT. Можно будет указать, какие типы сообщений включать
            в транскрипт, как обрабатывать системные события и броски кубиков.
          </p>
        </div>
      </SidePanel>

      <SidePanel
        isOpen={openPanel === 'merger-settings'}
        onClose={() => setOpenPanel(null)}
        title="Настройки мержера"
      >
        <div className="space-y-6">
          <p className="text-sm text-muted-foreground">
            Настройки алгоритма объединения событий. Можно будет выбрать приоритет источников,
            способ разрешения конфликтов временных меток и параметры синхронизации.
          </p>
        </div>
      </SidePanel>

      <SidePanel
        isOpen={openPanel === 'output-settings'}
        onClose={() => setOpenPanel(null)}
        title="Настройки вывода"
      >
        <div className="space-y-6">
          <p className="text-sm text-muted-foreground">
            Настройки рендерера и формата вывода. Можно будет выбрать формат файла (TXT, Markdown, JSON, HTML),
            шаблон форматирования, имя файла и путь сохранения.
          </p>
        </div>
      </SidePanel>

      <SidePanel
        isOpen={openPanel === 'add-source'}
        onClose={() => setOpenPanel(null)}
        title="Добавить источник"
      >
        <div className="space-y-6">
          <div className="space-y-4">
            <div>
              <h3 className="text-sm font-medium mb-3 text-muted-foreground uppercase tracking-wide">Аудио</h3>
              <div className="space-y-2">
                <button className="w-full text-left p-4 border border-border rounded-lg hover:border-accent hover:bg-accent/5 transition-colors">
                  <div className="flex items-start gap-3">
                    <AudioWaveform size={20} className="text-accent mt-0.5" />
                    <div className="flex-1">
                      <h4 className="font-medium mb-1">Multi-track Audio (Craig)</h4>
                      <p className="text-xs text-muted-foreground mb-2">
                        Тип: Аудио · Модель: GigaAM-v3 RNNT
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Распознавание речи из многодорожечных FLAC-записей Discord бота Craig.
                        Каждый участник обрабатывается отдельно.
                      </p>
                    </div>
                  </div>
                </button>

                <button className="w-full text-left p-4 border border-border rounded-lg hover:border-accent hover:bg-accent/5 transition-colors">
                  <div className="flex items-start gap-3">
                    <AudioWaveform size={20} className="text-accent mt-0.5" />
                    <div className="flex-1">
                      <h4 className="font-medium mb-1">Single Audio File</h4>
                      <p className="text-xs text-muted-foreground mb-2">
                        Тип: Аудио · Модель: Whisper Large v3
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Распознавание речи из одного аудиофайла. Подходит для записей с одним микрофоном
                        или готовых миксов.
                      </p>
                    </div>
                  </div>
                </button>
              </div>
            </div>

            <div>
              <h3 className="text-sm font-medium mb-3 text-muted-foreground uppercase tracking-wide">Чат и логи</h3>
              <div className="space-y-2">
                <button className="w-full text-left p-4 border border-border rounded-lg hover:border-accent hover:bg-accent/5 transition-colors">
                  <div className="flex items-start gap-3">
                    <MessageSquare size={20} className="text-accent mt-0.5" />
                    <div className="flex-1">
                      <h4 className="font-medium mb-1">Foundry VTT Chat Log</h4>
                      <p className="text-xs text-muted-foreground mb-2">
                        Тип: Чат · Формат: SQLite database
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Импорт сообщений, бросков кубиков и системных событий из чат-лога Foundry Virtual Tabletop.
                      </p>
                    </div>
                  </div>
                </button>

                <button className="w-full text-left p-4 border border-border rounded-lg hover:border-accent hover:bg-accent/5 transition-colors">
                  <div className="flex items-start gap-3">
                    <MessageSquare size={20} className="text-accent mt-0.5" />
                    <div className="flex-1">
                      <h4 className="font-medium mb-1">Discord Chat Export</h4>
                      <p className="text-xs text-muted-foreground mb-2">
                        Тип: Чат · Формат: JSON
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Импорт текстовых сообщений из экспорта Discord чата. Синхронизируется с аудио по времени.
                      </p>
                    </div>
                  </div>
                </button>
              </div>
            </div>
          </div>
        </div>
      </SidePanel>

      {/* Confirm Dialog */}
      <ConfirmDialog
        isOpen={showClearCacheDialog}
        onClose={() => setShowClearCacheDialog(false)}
        onConfirm={() => {
          console.log('Cache cleared');
        }}
        title="Очистить кэш сессии?"
        message="Все сохранённые результаты распознавания речи для этой сессии будут удалены. При следующей обработке все аудиодорожки будут распознаны заново. Это действие нельзя отменить."
        confirmText="Очистить"
        cancelText="Отмена"
      />
    </div>
  );
}