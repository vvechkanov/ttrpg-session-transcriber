import { useEffect, useState } from 'react';
import { X, AudioWaveform } from 'lucide-react';

interface SidePanelProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  icon?: 'audio' | 'chat' | 'clock' | 'file';
  children: React.ReactNode;
  showFooter?: boolean;
  isDirty?: boolean;
  onSave?: () => void;
}

export function SidePanel({
  isOpen,
  onClose,
  title,
  subtitle,
  icon,
  children,
  showFooter = false,
  isDirty = false,
  onSave
}: SidePanelProps) {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const IconComponent = icon === 'audio' ? AudioWaveform : null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-foreground/20 z-40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed top-0 right-0 h-full w-[480px] bg-card shadow-[0_0_48px_rgba(107,98,90,0.3)] z-50 flex flex-col animate-slide-in">
        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b border-border">
          <div className="flex items-start gap-3">
            {IconComponent && (
              <div className="mt-1">
                <IconComponent size={20} className="text-accent" />
              </div>
            )}
            <div>
              <h2 className="text-lg font-medium">{title}</h2>
              {subtitle && (
                <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <X size={24} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {children}
        </div>

        {/* Footer */}
        {showFooter && (
          <div className="border-t border-border p-6 flex items-center justify-between">
            <div className="flex items-center gap-2">
              {isDirty && (
                <>
                  <div className="w-2 h-2 rounded-full bg-accent" />
                  <span className="text-sm text-accent">Есть несохранённые изменения</span>
                </>
              )}
            </div>
            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm text-foreground hover:bg-secondary rounded-lg transition-colors"
              >
                Отмена
              </button>
              <button
                onClick={onSave}
                disabled={!isDirty}
                className={`px-4 py-2 text-sm rounded-lg transition-colors ${
                  isDirty
                    ? 'bg-accent text-accent-foreground hover:bg-accent/90'
                    : 'bg-muted text-muted-foreground cursor-not-allowed'
                }`}
              >
                Сохранить
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
