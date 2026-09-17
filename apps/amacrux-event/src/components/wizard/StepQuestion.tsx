"use client";

import { OptionCard } from "@/components/ui/OptionCard";
import { OptionGrid } from "@/components/ui/OptionGrid";
import type { Question } from "@/domain/questions";

export interface StepQuestionProps {
  question: Question;
  value: string | string[] | undefined;
  onChange: (value: string | string[]) => void;
}

export function StepQuestion({ question, value, onChange }: StepQuestionProps) {
  if (question.type === "multi") {
    const selected = Array.isArray(value) ? value : [];
    const max = question.max ?? question.options.length;
    const full = selected.length >= max;
    return (
      <OptionGrid legend={question.title} hint={question.hint} mode="multi" columns={question.columns} status={`${selected.length} de ${max}`}>
        {question.options.map((o) => {
          const isSelected = selected.includes(o.value);
          return (
            <OptionCard
              key={o.value}
              mode="multi"
              label={o.label}
              selected={isSelected}
              disabled={full && !isSelected}
              pill
              onToggle={() => onChange(isSelected ? selected.filter((v) => v !== o.value) : [...selected, o.value])}
            />
          );
        })}
      </OptionGrid>
    );
  }

  return (
    <OptionGrid legend={question.title} hint={question.hint} mode="single" columns={question.columns}>
      {question.options.map((o) => (
        <OptionCard key={o.value} mode="single" label={o.label} description={o.description} selected={value === o.value} compact={question.type !== "scale"} onToggle={() => onChange(o.value)} />
      ))}
    </OptionGrid>
  );
}
