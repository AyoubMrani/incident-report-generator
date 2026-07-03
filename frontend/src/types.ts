export type BlockType = 
  | 'heading' 
  | 'paragraph' 
  | 'list' 
  | 'incident_example' 
  | 'code' 
  | 'image' 
  | 'table';

export interface BaseBlock {
  id: string;
  type: BlockType;
}

export interface HeadingBlock extends BaseBlock {
  type: 'heading';
  level: 1 | 2 | 3 | 4;
  content: string;
  title?: string;
}

export interface ParagraphBlock extends BaseBlock {
  type: 'paragraph';
  content: string; // Quill Delta format as JSON string, or plain text for backward compatibility
  title?: string;
}

export interface ListBlock extends BaseBlock {
  type: 'list';
  ordered: boolean;
  items: string[];
  label?: string; // Optional label - when set, renders as description box
  title?: string;
}

export interface IncidentExampleBlock extends BaseBlock {
  type: 'incident_example';
  incident_id: string;
  link?: string;
  title?: string;
}

export interface CodeSnippet {
  id: string;
  type: 'code';
  title: string;
  header: string;
  language: string;
  content: string;
}

export interface CodeDescription {
  id: string;
  type: 'description';
  title: string;
  content: string; // Quill HTML
}

export type CodeItem = CodeSnippet | CodeDescription;

export interface CodeBlock extends BaseBlock {
  type: 'code';
  items: CodeItem[];
}

export interface ImageBlock extends BaseBlock {
  type: 'image';
  data_url: string;
  caption: string;
  title?: string;
}

export interface TableBlock extends BaseBlock {
  type: 'table';
  headers: string[];
  rows: string[][];
  title?: string;
}

export type ContentBlock = 
  | HeadingBlock 
  | ParagraphBlock 
  | ListBlock 
  | IncidentExampleBlock 
  | CodeBlock 
  | ImageBlock 
  | TableBlock;

export interface ReportMetadata {
  incident_id: string;
  title: string;
  caller: string;
  category: string;
  subcategory: string;
  date: string;
  [key: string]: string;
}

export interface IncidentReport {
  metadata: ReportMetadata;
  blocks: ContentBlock[];
}

export interface StoredCategoryOption {
  id: string;
  label: string;
}

export interface StoredMetadataField {
  id: string;
  name: string;
  label: string;
}
