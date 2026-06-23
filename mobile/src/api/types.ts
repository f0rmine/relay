export interface User {
  id: string;
  username: string;
  email?: string;
  display_name: string;
  avatar_url?: string | null;
  created_at?: string;
  last_seen_at?: string | null;
  is_online?: boolean;
}

export interface Attachment {
  id: string;
  message_id?: string | null;
  uploader_id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  public_url: string;
  created_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender_id: string;
  text?: string | null;
  created_at: string;
  updated_at: string;
  edited_at?: string | null;
  deleted_at?: string | null;
  deleted_by_id?: string | null;
  attachments: Attachment[];
  read_by: string[];
  request_id?: string;
}

export interface Conversation {
  id: string;
  kind: string;
  participants: User[];
  latest_message?: Message | null;
  unread_count: number;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}
