import type { Template } from '@/api/generation';

interface TemplateCardProps {
  template: Template;
  selected: boolean;
  onSelect: () => void;
}

export default function TemplateCard({ template, selected, onSelect }: TemplateCardProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`rounded-lg border p-3 text-left transition-colors ${
        selected ? 'border-indigo-500 bg-indigo-950' : 'border-gray-700 bg-gray-900 hover:border-gray-600'
      }`}
    >
      <p className="font-medium text-white text-sm">{template.name}</p>
      <p className="mt-1 text-xs text-gray-400 line-clamp-2">{template.description}</p>
    </button>
  );
}
