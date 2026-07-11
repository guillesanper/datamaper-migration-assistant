/**
 * Centralized icon exports for better tree-shaking
 * Import icons from here instead of directly from lucide-react
 */

// All icons used in the application
export {
  // Navigation & UI
  ChevronDown,
  ChevronRight,
  ChevronUp,
  X,
  Plus,
  Settings,
  Eye,
  EyeOff,
  MoreVertical,

  // Database & Tables
  Database,
  Key,
  Lock,
  Table as TableIcon,
  Grid3x3,
  Layers,

  // Actions
  Search,
  Trash2,
  Edit,
  Upload,
  Download,
  RefreshCw,
  History,
  Maximize2,
  Minimize2,
  Filter,
  Save,
  Play,

  // Status & Feedback
  AlertCircle,
  CheckCircle2,
  AlertTriangle,

  // Links & Connections
  Link2,
  Unlink,

  // Files
  FileText,
  FileSpreadsheet,

  // Misc
  MousePointer2,
  Grid,
} from 'lucide-react';

// Also export Table for components that use it directly
export { Table } from 'lucide-react';

// Export CheckCircle as alias for CheckCircle2 for backward compatibility
export { CheckCircle2 as CheckCircle } from 'lucide-react';

// Export type for LucideIcon
export type { LucideIcon } from 'lucide-react';
