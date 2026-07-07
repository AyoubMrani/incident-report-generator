import React, { useMemo } from 'react';
import ReactQuill, { Quill } from 'react-quill';
import 'react-quill/dist/quill.snow.css';

interface Props {
  content: string;
  onChange: (content: string) => void;
}

const QUILL_MODULES = {
  toolbar: [
    [{ header: [1, 2, 3, 4, false] }],
    ['bold', 'italic', 'underline', 'strike'],
    [{ color: [] }, { background: [] }],
    [{ align: [] }],
    [{ list: 'ordered' }, { list: 'bullet' }],
    ['blockquote', 'code-block'],
    ['link', 'image'],
    ['clean']
  ]
};

const QUILL_FORMATS = [
  'header',
  'bold',
  'italic',
  'underline',
  'strike',
  'color',
  'background',
  'align',
  'list',
  'blockquote',
  'code-block',
  'link',
  'image'
];

export function QuillEditor({ content, onChange }: Props) {
  const editorRef = React.useRef<ReactQuill>(null);

  const handleChange = (value: string) => {
    onChange(value);
  };

  return (
    <div className="space-y-3 border border-gray-200 rounded-lg bg-white overflow-hidden">
      <ReactQuill
        ref={editorRef}
        theme="snow"
        value={content}
        onChange={handleChange}
        modules={QUILL_MODULES}
        formats={QUILL_FORMATS}
        placeholder="Type your paragraph here..."
        className="quill-editor bg-white min-h-64"
      />
    </div>
  );
}
