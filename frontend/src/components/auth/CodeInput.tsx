// src/components/auth/CodeInput.tsx
import React, { useRef, useEffect } from "react";

interface CodeInputProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  length?: number;
}

export const CodeInput: React.FC<CodeInputProps> = ({
  value,
  onChange,
  disabled = false,
  length = 8,
}) => {
  const inputsRef = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    // Auto-focus primer input al montar
    if (inputsRef.current[0] && !disabled) {
      inputsRef.current[0].focus();
    }
  }, [disabled]);

  const handleChange = (index: number, newValue: string) => {
    // Solo permitir números y letras
    if (newValue && !/^[0-9A-Z]$/.test(newValue.toUpperCase())) return;

    const newCode = value.split("");
    newCode[index] = newValue.toUpperCase();
    const updatedCode = newCode.join("");

    onChange(updatedCode.slice(0, length));

    // Auto-focus siguiente input si hay valor
    if (newValue && index < length - 1) {
      inputsRef.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !value[index] && index > 0) {
      // Si está vacío y presiona backspace, ir al anterior
      inputsRef.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    // Permitir números y letras (A-Z)
    const pastedData = e.clipboardData
      .getData("text/plain")
      .toUpperCase()
      .replace(/[^0-9A-Z]/g, "");
    
    const newCode = pastedData.slice(0, length);
    onChange(newCode);

    // Focus al último input lleno o al siguiente vacío
    const nextIndex = Math.min(newCode.length, length - 1);
    inputsRef.current[nextIndex]?.focus();
  };

  return (
    <div className="code-input-container">
      {Array.from({ length }).map((_, index) => (
        <input
          key={index}
          ref={(el) => {inputsRef.current[index] = el}}
          type="text"
          inputMode="text"
          maxLength={1}
          value={value[index] || ""}
          onChange={(e) => handleChange(index, e.target.value)}
          onKeyDown={(e) => handleKeyDown(index, e)}
          onPaste={handlePaste}
          disabled={disabled}
          className="code-input-digit"
          autoComplete="off"
        />
      ))}
    </div>
  );
};