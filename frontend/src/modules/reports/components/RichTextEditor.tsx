import React, { useRef, useState } from 'react';
import { RichTextContent, StyledTextSegment, InlineImageSegment } from '../../../types';
import { Bold, Italic, Underline, Trash2, Image as ImageIcon, Type } from 'lucide-react';

interface Props {
  content: RichTextContent | string;
  onChange: (content: RichTextContent) => void;
  textAlign?: 'left' | 'center' | 'right' | 'justify';
  onTextAlignChange?: (align: 'left' | 'center' | 'right' | 'justify') => void;
}

export function RichTextEditor({ content, onChange, textAlign = 'left', onTextAlignChange }: Props) {
  const [plainText, setPlainText] = useState<string>(() => {
    if (typeof content === 'string') {
      return content;
    }
    return content.map(seg => seg.type === 'text' ? seg.content : '[Image]').join('');
  });

  const [selectedText, setSelectedText] = useState('');
  const [showColorPicker, setShowColorPicker] = useState(false);
  const [showFontSizeMenu, setShowFontSizeMenu] = useState(false);
  const [selectedColor, setSelectedColor] = useState('#000000');
  const [selectedFontSize, setSelectedFontSize] = useState(16);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const convertPlainToRichText = (text: string): RichTextContent => {
    return text ? [{ type: 'text', content: text }] : [];
  };

  const applyFormatting = (format: 'bold' | 'italic' | 'underline' | 'strikethrough' | 'color' | 'fontSize') => {
    const textarea = document.querySelector('textarea') as HTMLTextAreaElement;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selected = plainText.substring(start, end);

    if (!selected) {
      alert('Please select text to format');
      return;
    }

    const before = plainText.substring(0, start);
    const after = plainText.substring(end);

    const newPlainText = before + selected + after;
    setPlainText(newPlainText);
    setSelectedText(selected);

    if (format === 'color') {
      setShowColorPicker(true);
      return;
    }

    if (format === 'fontSize') {
      setShowFontSizeMenu(true);
      return;
    }

    // Create rich text with applied formatting
    const richContent: RichTextContent = [
      { type: 'text', content: before },
      {
        type: 'text',
        content: selected,
        [format]: true,
        ...(format === 'color' && { color: selectedColor }),
        ...(format === 'fontSize' && { fontSize: selectedFontSize })
      } as StyledTextSegment,
      { type: 'text', content: after }
    ].filter(seg => seg.type !== 'text' || seg.content);

    onChange(richContent);
  };

  const applyColor = (color: string) => {
    setSelectedColor(color);
    const richContent: RichTextContent = [
      { type: 'text', content: plainText.substring(0, plainText.indexOf(selectedText)) },
      {
        type: 'text',
        content: selectedText,
        color: color
      },
      { type: 'text', content: plainText.substring(plainText.indexOf(selectedText) + selectedText.length) }
    ].filter(seg => seg.content);

    onChange(richContent);
    setShowColorPicker(false);
  };

  const applyFontSize = (size: number) => {
    setSelectedFontSize(size);
    const richContent: RichTextContent = [
      { type: 'text', content: plainText.substring(0, plainText.indexOf(selectedText)) },
      {
        type: 'text',
        content: selectedText,
        fontSize: size
      },
      { type: 'text', content: plainText.substring(plainText.indexOf(selectedText) + selectedText.length) }
    ].filter(seg => seg.content);

    onChange(richContent);
    setShowFontSizeMenu(false);
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        const textarea = document.querySelector('textarea') as HTMLTextAreaElement;
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;

        const before = plainText.substring(0, start);
        const after = plainText.substring(end);
        const newPlainText = before + '[Image]' + after;
        setPlainText(newPlainText);

        const richContent: RichTextContent = [
          before && { type: 'text', content: before },
          { type: 'image', data_url: reader.result as string, alt: 'User inserted image' },
          after && { type: 'text', content: after }
        ].filter(Boolean) as RichTextContent;

        onChange(richContent);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleTextChange = (text: string) => {
    setPlainText(text);
    // For now, just convert to simple rich text
    onChange(convertPlainToRichText(text));
  };

  const colors = ['#000000', '#1f2937', '#dc2626', '#ea580c', '#f59e0b', '#10b981', '#0891b2', '#3b82f6', '#6366f1', '#8b5cf6'];
  const fontSizes = [12, 14, 16, 18, 20, 24, 28, 32];

  return (
    <div className="space-y-3 border border-gray-200 rounded-lg p-3 bg-gray-50">
      {/* Toolbar */}
      <div className="flex flex-wrap gap-2 items-center border-b border-gray-200 pb-3">
        {/* Text Alignment */}
        <div className="flex gap-1 border-r border-gray-200 pr-2">
          {(['left', 'center', 'right', 'justify'] as const).map(align => (
            <button
              key={align}
              onClick={() => onTextAlignChange?.(align)}
              className={`px-2 py-1 text-xs rounded capitalize transition-colors ${
                textAlign === align
                  ? 'bg-blue-500 text-white'
                  : 'bg-white text-gray-600 hover:bg-gray-100'
              }`}
              title={`Align ${align}`}
            >
              {align[0].toUpperCase()}
            </button>
          ))}
        </div>

        {/* Text Formatting */}
        <div className="flex gap-1 border-r border-gray-200 pr-2">
          <button
            onClick={() => applyFormatting('bold')}
            className="p-1 text-gray-600 hover:bg-gray-100 rounded transition-colors"
            title="Bold"
          >
            <Bold className="w-4 h-4" />
          </button>
          <button
            onClick={() => applyFormatting('italic')}
            className="p-1 text-gray-600 hover:bg-gray-100 rounded transition-colors"
            title="Italic"
          >
            <Italic className="w-4 h-4" />
          </button>
          <button
            onClick={() => applyFormatting('underline')}
            className="p-1 text-gray-600 hover:bg-gray-100 rounded transition-colors"
            title="Underline"
          >
            <Underline className="w-4 h-4" />
          </button>
          <button
            onClick={() => applyFormatting('strikethrough')}
            className="p-1 text-gray-600 hover:bg-gray-100 rounded transition-colors font-bold text-sm"
            title="Strikethrough"
          >
            S̶
          </button>
        </div>

        {/* Font Size */}
        <div className="relative border-r border-gray-200 pr-2">
          <button
            onClick={() => setShowFontSizeMenu(!showFontSizeMenu)}
            className="flex items-center gap-1 px-2 py-1 text-xs bg-white text-gray-600 hover:bg-gray-100 rounded transition-colors"
            title="Font Size"
          >
            <Type className="w-4 h-4" />
            {selectedFontSize}px
          </button>
          {showFontSizeMenu && (
            <div className="absolute top-full left-0 mt-1 bg-white border border-gray-200 rounded shadow-lg z-10">
              {fontSizes.map(size => (
                <button
                  key={size}
                  onClick={() => applyFontSize(size)}
                  className="block w-full text-left px-3 py-1 text-sm hover:bg-blue-100 text-gray-700 border-b border-gray-100 last:border-b-0"
                >
                  {size}px
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Color Picker */}
        <div className="relative border-r border-gray-200 pr-2">
          <button
            onClick={() => setShowColorPicker(!showColorPicker)}
            className="flex items-center gap-1 px-2 py-1 text-xs bg-white text-gray-600 hover:bg-gray-100 rounded transition-colors"
            title="Text Color"
          >
            <div
              className="w-4 h-4 rounded border border-gray-300"
              style={{ backgroundColor: selectedColor }}
            />
            Color
          </button>
          {showColorPicker && (
            <div className="absolute top-full left-0 mt-1 bg-white border border-gray-200 rounded shadow-lg z-10 p-2 flex gap-1 flex-wrap w-40">
              {colors.map(color => (
                <button
                  key={color}
                  onClick={() => applyColor(color)}
                  className="w-6 h-6 rounded border-2 transition-transform hover:scale-110"
                  style={{
                    backgroundColor: color,
                    borderColor: selectedColor === color ? '#000' : '#ddd'
                  }}
                  title={color}
                />
              ))}
            </div>
          )}
        </div>

        {/* Image Insert */}
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-1 px-2 py-1 text-xs bg-white text-gray-600 hover:bg-gray-100 rounded transition-colors"
          title="Insert Image"
        >
          <ImageIcon className="w-4 h-4" />
          Image
        </button>
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleImageUpload}
          accept="image/*"
          className="hidden"
        />
      </div>

      {/* Text Editor */}
      <textarea
        value={plainText}
        onChange={(e) => handleTextChange(e.target.value)}
        placeholder="Type your paragraph here... Select text to apply formatting."
        className="w-full p-3 border border-gray-200 rounded bg-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-200 resize-y min-h-[120px]"
        style={{ textAlign }}
      />

      {/* Preview */}
      {Array.isArray(content) && content.length > 0 && (
        <div className="border-t border-gray-200 pt-3">
          <p className="text-xs font-semibold text-gray-600 mb-2">Preview:</p>
          <div
            className="p-3 bg-white rounded border border-gray-200 prose prose-sm max-w-none"
            style={{ textAlign }}
          >
            {content.map((segment, idx) =>
              segment.type === 'text' ? (
                <span
                  key={idx}
                  style={{
                    fontWeight: segment.bold ? 'bold' : 'normal',
                    fontStyle: segment.italic ? 'italic' : 'normal',
                    textDecoration: segment.strikethrough
                      ? 'line-through'
                      : segment.underline
                      ? 'underline'
                      : 'none',
                    color: segment.color || 'inherit',
                    fontSize: segment.fontSize ? `${segment.fontSize}px` : 'inherit'
                  }}
                >
                  {segment.content}
                </span>
              ) : (
                <div key={idx} className="my-2 inline-block">
                  <img
                    src={segment.data_url}
                    alt={segment.alt || 'Inline image'}
                    className="max-h-32 max-w-full rounded border border-gray-200"
                    style={{
                      width: segment.width ? `${segment.width}px` : 'auto',
                      height: segment.height ? `${segment.height}px` : 'auto'
                    }}
                  />
                </div>
              )
            )}
          </div>
        </div>
      )}

      <div className="text-xs text-gray-500">
        💡 Select text and use the toolbar to apply formatting. Insert images directly into your paragraph.
      </div>
    </div>
  );
}
