/**
 * Icon.tsx —— 全站统一图标组件（Ant Design 官方图标 @ant-design/icons 6.x）
 *
 * 2026-10-18 改版：放弃自托管 iconfont（字形映射不全导致空白），统一改用
 * Ant Design 官方图标库，与 antd/antdx 组件同源，风格与尺寸刻度天然一致。
 * 语义名 → 官方图标组件的映射集中在 ICONS，调用点只写语义名：
 *   <Icon name="database" size={14} />  <Icon name="send" size={16} />
 *
 * 设计规范（参考 https://ant.design/design.md）：
 * - 图标以文字尺寸为基准（fontSize 控制，SVG 自动 1em 缩放）
 * - 颜色默认继承 currentColor，由父级语义令牌控制（不硬编码色值）
 * - 与文字并排时保持 4px/8px 栅格间距（调用方用 gap 控制）
 */
import type { ComponentType, CSSProperties } from 'react'
import {
  AimOutlined,
  ApiOutlined,
  AppstoreOutlined,
  ArrowUpOutlined,
  BarChartOutlined,
  BulbOutlined,
  CheckCircleOutlined,
  CheckOutlined,
  ClockCircleOutlined,
  CloseOutlined,
  ClusterOutlined,
  CodeOutlined,
  ControlOutlined,
  CopyOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DislikeOutlined,
  DownloadOutlined,
  DownOutlined,
  EditOutlined,
  ExperimentOutlined,
  ExportOutlined,
  EyeOutlined,
  FileTextOutlined,
  FilterOutlined,
  FolderOutlined,
  FundOutlined,
  GlobalOutlined,
  HourglassOutlined,
  InboxOutlined,
  InfoCircleOutlined,
  LeftOutlined,
  LikeOutlined,
  LineChartOutlined,
  LoadingOutlined,
  LoginOutlined,
  LogoutOutlined,
  MessageOutlined,
  MoneyCollectOutlined,
  MoonOutlined,
  MoreOutlined,
  PaperClipOutlined,
  PartitionOutlined,
  PieChartOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReadOutlined,
  ReloadOutlined,
  RightOutlined,
  RobotOutlined,
  RollbackOutlined,
  SafetyCertificateOutlined,
  SafetyOutlined,
  SearchOutlined,
  SendOutlined,
  SettingOutlined,
  SmileOutlined,
  SortDescendingOutlined,
  StarOutlined,
  StopOutlined,
  SunOutlined,
  TableOutlined,
  ThunderboltOutlined,
  ToolOutlined,
  UnorderedListOutlined,
  UserOutlined,
  WarningOutlined,
} from '@ant-design/icons'

/** 语义名 → Ant Design 官方图标组件（键为全站调用口径，勿随意改名） */
const ICONS = {
  /* 数据与图表 */
  database: DatabaseOutlined,
  table: TableOutlined,
  chart: BarChartOutlined,
  lineChart: LineChartOutlined,
  pieChart: PieChartOutlined,
  fileChart: FundOutlined,
  mindMap: PartitionOutlined,
  /* 文本与文件 */
  fileText: FileTextOutlined,
  attachment: PaperClipOutlined,
  download: DownloadOutlined,
  externalLink: ExportOutlined,
  bookMarked: ReadOutlined,
  /* 搜索与思考 */
  search: SearchOutlined,
  brain: BulbOutlined,
  bulb: BulbOutlined,
  magic: ThunderboltOutlined,
  robot: RobotOutlined,
  sparkles: StarOutlined,
  globe: GlobalOutlined,
  /* 操作 */
  send: SendOutlined,
  arrowUp: ArrowUpOutlined,
  arrowDown: DownOutlined,
  arrowLeft: LeftOutlined,
  arrowRight: RightOutlined,
  add: PlusOutlined,
  close: CloseOutlined,
  check: CheckOutlined,
  checkDouble: CheckCircleOutlined,
  copy: CopyOutlined,
  refresh: ReloadOutlined,
  edit: EditOutlined,
  trash: DeleteOutlined,
  archive: InboxOutlined,
  unarchive: RollbackOutlined,
  more: MoreOutlined,
  stop: StopOutlined,
  play: PlayCircleOutlined,
  loader: LoadingOutlined,
  filter: FilterOutlined,
  sortDesc: SortDescendingOutlined,
  uploaded: LoginOutlined,
  /* 账户与系统 */
  user: UserOutlined,
  userSmile: SmileOutlined,
  logout: LogoutOutlined,
  settings: SettingOutlined,
  equalizer: ControlOutlined,
  shield: SafetyOutlined,
  shieldCheck: SafetyCertificateOutlined,
  command: ApiOutlined,
  code: CodeOutlined,
  moon: MoonOutlined,
  sun: SunOutlined,
  eye: EyeOutlined,
  star: StarOutlined,
  clock: ClockCircleOutlined,
  hourglass: HourglassOutlined,
  /* 统计读数 */
  speed: DashboardOutlined,
  dashboard: DashboardOutlined,
  coins: MoneyCollectOutlined,
  stack: AppstoreOutlined,
  cpu: ClusterOutlined,
  flowChart: PartitionOutlined,
  grid: AppstoreOutlined,
  /* 反馈与状态 */
  thumbUp: LikeOutlined,
  thumbDown: DislikeOutlined,
  warn: WarningOutlined,
  info: InfoCircleOutlined,
  /* 会话与工具 */
  chat: MessageOutlined,
  folder: FolderOutlined,
  tools: ToolOutlined,
  wrench: ToolOutlined,
  target: AimOutlined,
  listCheck: UnorderedListOutlined,
  experiment: ExperimentOutlined,
} as const satisfies Record<string, ComponentType<{ style?: CSSProperties; className?: string }>>

export type IconName = keyof typeof ICONS

export interface IconProps {
  name: IconName
  /** 字号（px），官方图标以 1em 比例缩放，默认 14 */
  size?: number
  /** 颜色，默认继承 currentColor */
  color?: string
  className?: string
  style?: CSSProperties
  /** 悬浮说明（无障碍 title） */
  title?: string
}

export default function Icon({ name, size = 14, color, className, style, title }: IconProps) {
  const Glyph = ICONS[name]
  const node = <Glyph className={className} style={{ fontSize: size, color, ...style }} />
  if (!title) return node
  return <span title={title} className="inline-flex items-center">{node}</span>
}
