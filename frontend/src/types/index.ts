export interface Account {
  id: string
  name: string
  enabled: boolean
  device?: string
  douyin_nickname?: string
  display_name?: string
  dir?: string
  is_default?: boolean
  session_status?: string
  login_checked_at?: string | null
  login_check_reason?: string
  running?: boolean
  state_file_exists?: boolean
  created_at?: string
  updated_at?: string
  last_run?: string | null
  next_run?: string | null
  next_harvest?: string | null
  contacts_fetching?: boolean
  harvesting?: boolean
  auto_run_enabled?: boolean
  selected_count?: number
}

export interface ScanStatus {
  status: string
  message: string
  qrcode: string
  error?: string
}

export interface Contact {
  id: string
  name: string
  streak?: string
  avatar?: string
  selected?: boolean
  has_conversation?: boolean
  channel?: string
  identity_ambiguous?: boolean
  /** 今日实际发送结果：succeeded / failed / uncertain / skipped；空表示今日未执行。 */
  today_status?: string | null
  today_reason?: string
  today_at?: string
}

export interface RunRecord {
  id: number
  account_id: string
  task_type: string
  started_at?: string
  finished_at?: string
  status: string
  success_count: number
  failed_count: number
  risk_detected: boolean
  error?: string | null
  artifact?: boolean
}

export interface RunItem {
  id: number
  run_id: number
  friend_name: string
  status: string
  error?: string | null
  message_preview?: string | null
}
