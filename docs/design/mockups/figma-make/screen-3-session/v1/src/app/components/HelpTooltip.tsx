import { useState, useRef, useEffect } from 'react';
import { HelpCircle, X } from 'lucide-react';

interface HelpTooltipProps {
  content: string;
  size?: number;
}

export function HelpTooltip({ content, size = 18 }: HelpTooltipProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const buttonRef = useRef<HTMLButtonElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      const tooltipWidth = 320;

      // Position to the right of the button if there's space, otherwise to the left
      let left = rect.right + 8;
      if (left + tooltipWidth > window.innerWidth - 16) {
        left = rect.left - tooltipWidth - 8;
      }

      setPosition({
        top: rect.top,
        left: left
      });
    }
  }, [isOpen]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        tooltipRef.current &&
        buttonRef.current &&
        !tooltipRef.current.contains(event.target as Node) &&
        !buttonRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  return (
    <>
      <button
        ref={buttonRef}
        onClick={() => setIsOpen(!isOpen)}
        className="text-muted-foreground hover:text-foreground transition-colors"
      >
        <HelpCircle size={size} />
      </button>

      {isOpen && (
        <div
          ref={tooltipRef}
          className="fixed z-50 w-80 bg-card border border-border rounded-xl shadow-[0_8px_24px_rgba(107,98,90,0.2)] p-5"
          style={{ top: `${position.top}px`, left: `${position.left}px` }}
        >
          <div className="flex items-start justify-between mb-3">
            <h4 className="font-medium">Справка</h4>
            <button
              onClick={() => setIsOpen(false)}
              className="text-muted-foreground hover:text-foreground transition-colors -mt-1"
            >
              <X size={18} />
            </button>
          </div>
          <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">
            {content}
          </p>
        </div>
      )}
    </>
  );
}
