// src/components/mapping/GridTableView.tsx
import React, { useState, useMemo } from "react";
import {
  Plus,
  Trash2,
  Search,
  ArrowUpDown,
  Save,
  X,
} from "lucide-react";
import { mappingService } from "../../services/mapping_service";
import type { Mapping, TableWithColumns} from "../../types/mapping-types";
import type { Project } from "../../types/project_types";
import type { ConnectorTable } from "../../types/db_connection_types";
import { connectorTablesToTableWithColumns } from "../../utils/connectorUtils";
import { useTranslation } from 'react-i18next';
import { toast } from "../../utils/toast";
import { getApiError } from "../../utils/apiError";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import styles from "../../styles/mapping/mapping.module.css";

interface GridTableViewProps {
  projectId: string;
  project: Project | null;
  tables: TableWithColumns[];
  mappings: Mapping[];
  onRefresh: () => void;
  connectorTables?: ConnectorTable[];
}

type SortField = "origin_table" | "origin_column" | "destination_table" | "destination_column";
type SortDirection = "asc" | "desc";

export const GridTableView: React.FC<GridTableViewProps> = ({
  projectId,
  tables: importedTables,
  mappings: initialMappings,
  onRefresh,
  connectorTables = [],
}) => {
  const { t } = useTranslation('common');
  const tables: TableWithColumns[] = useMemo(
    () => [...importedTables, ...connectorTablesToTableWithColumns(connectorTables)],
    [importedTables, connectorTables]
  );
  const [mappings, setMappings] = useState(initialMappings);
  const [searchQuery, setSearchQuery] = useState("");
  const [sortField, setSortField] = useState<SortField>("origin_table");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [newMapping, setNewMapping] = useState<Partial<Mapping>>({});
  const [isAddingNew, setIsAddingNew] = useState(false);

  const originTables = tables.filter((t) => t.type === "origin");
  const destTables = tables.filter((t) => t.type === "destination");

  // Filtrado y ordenamiento
  const filteredAndSortedMappings = useMemo(() => {
    let result = [...mappings];

    // Filtrar
    if (searchQuery) {
      result = result.filter(
        (m) =>
          m.origin_table.toLowerCase().includes(searchQuery.toLowerCase()) ||
          m.origin_column.toLowerCase().includes(searchQuery.toLowerCase()) ||
          m.destination_table.toLowerCase().includes(searchQuery.toLowerCase()) ||
          m.destination_column.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }

    // Ordenar
    result.sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];
      const comparison = aVal.localeCompare(bVal);
      return sortDirection === "asc" ? comparison : -comparison;
    });

    return result;
  }, [mappings, searchQuery, sortField, sortDirection]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDirection("asc");
    }
  };

  const handleDeleteMapping = async (mapping: Mapping) => {
    if (!confirm("¿Eliminar este mapeo?")) return;

    try {
      await mappingService.deleteMapping(mapping);
      setMappings(
        mappings.filter(
          (m) =>
            !(
              m.origin_table === mapping.origin_table &&
              m.origin_column === mapping.origin_column &&
              m.destination_table === mapping.destination_table &&
              m.destination_column === mapping.destination_column
            )
        )
      );
      toast.success("Mapeo eliminado");
      onRefresh();
    } catch (error) {
      console.error("Error deleting mapping:", error);
      toast.error(getApiError(error, t));
    }
  };

  const handleAddMapping = async () => {
    if (
      !newMapping.origin_table ||
      !newMapping.origin_column ||
      !newMapping.destination_table ||
      !newMapping.destination_column
    ) {
      toast.error(t('errors.required'));
      return;
    }

    try {
      const mapping: Mapping = {
        project_id: projectId,
        origin_table: newMapping.origin_table,
        origin_column: newMapping.origin_column,
        destination_table: newMapping.destination_table,
        destination_column: newMapping.destination_column,
        notes: newMapping.notes,
      };

      await mappingService.createMapping(mapping);
      setMappings([...mappings, mapping]);
      setNewMapping({});
      setIsAddingNew(false);
      toast.success("Mapeo creado");
      onRefresh();
    } catch (error: unknown) {
      console.error("Error creating mapping:", error);
      toast.error(getApiError(error, t));
    }
  };

  const getColumnsForTable = (tableName: string, type: "origin" | "destination") => {
    const table = tables.find((t) => t.name === tableName && t.type === type);
    return table?.columns || [];
  };

  return (
    <div className={styles.gridContainer}>
      {/* Toolbar */}
      <div className={styles.toolbar}>
        <div className={styles.toolbarLeft}>
          <button onClick={() => setIsAddingNew(true)} className={styles.toolbarButtonPrimary}>
            <Plus className="w-4 h-4" />
            Nuevo Mapeo
          </button>
        </div>

        <div className={styles.toolbarRight}>
          <div className={styles.columnPanelSearch}>
            <Search className={styles.columnPanelSearchIcon} />
            <input
              type="text"
              placeholder="Buscar mapeos..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className={styles.columnPanelSearchInput}
            />
          </div>
          <div className={styles.toolbarInfo}>
            <span className="font-semibold">{filteredAndSortedMappings.length}</span> de{" "}
            <span className="font-semibold">{mappings.length}</span> mapeos
          </div>
        </div>
      </div>

      {/* Table */}
      <div className={styles.gridTableWrapper}>
        <table className={styles.gridTable}>
          <thead className={styles.gridTableHeader}>
            <tr>
              <th className={styles.gridTableHeaderCell}>
                <button
                  onClick={() => handleSort("origin_table")}
                  className={styles.gridTableHeaderButton}
                >
                  Tabla Origen
                  <ArrowUpDown className={styles.gridTableHeaderIcon} />
                </button>
              </th>
              <th className={styles.gridTableHeaderCell}>
                <button
                  onClick={() => handleSort("origin_column")}
                  className={styles.gridTableHeaderButton}
                >
                  Columna Origen
                  <ArrowUpDown className={styles.gridTableHeaderIcon} />
                </button>
              </th>
              <th className={`${styles.gridTableHeaderCell} ${styles.gridTableCellCenter}`}>
                <span className="text-muted-foreground">→</span>
              </th>
              <th className={styles.gridTableHeaderCell}>
                <button
                  onClick={() => handleSort("destination_table")}
                  className={styles.gridTableHeaderButton}
                >
                  Tabla Destino
                  <ArrowUpDown className={styles.gridTableHeaderIcon} />
                </button>
              </th>
              <th className={styles.gridTableHeaderCell}>
                <button
                  onClick={() => handleSort("destination_column")}
                  className={styles.gridTableHeaderButton}
                >
                  Columna Destino
                  <ArrowUpDown className={styles.gridTableHeaderIcon} />
                </button>
              </th>
              <th className={styles.gridTableHeaderCell}>Notas</th>
              <th className={`${styles.gridTableHeaderCell} ${styles.gridTableCellCenter} w-24`}>
                Acciones
              </th>
            </tr>
          </thead>
          <tbody className={styles.gridTableBody}>
            {/* Nueva fila */}
            {isAddingNew && (
              <tr className={styles.gridTableRowNew}>
                <td className={styles.gridTableCell}>
                  <Select
                    value={newMapping.origin_table || ""}
                    onValueChange={(value) => setNewMapping({ ...newMapping, origin_table: value })}
                  >
                    <SelectTrigger className={styles.gridTableSelect}>
                      <SelectValue placeholder="Seleccionar tabla..." />
                    </SelectTrigger>
                    <SelectContent>
                      {originTables.map((t) => (
                        <SelectItem key={t.id} value={t.name}>
                          {t.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </td>
                <td className={styles.gridTableCell}>
                  <Select
                    value={newMapping.origin_column || ""}
                    onValueChange={(value) => setNewMapping({ ...newMapping, origin_column: value })}
                    disabled={!newMapping.origin_table}
                  >
                    <SelectTrigger className={styles.gridTableSelect}>
                      <SelectValue placeholder="Seleccionar columna..." />
                    </SelectTrigger>
                    <SelectContent>
                      {newMapping.origin_table &&
                        getColumnsForTable(newMapping.origin_table, "origin").map((col) => (
                          <SelectItem key={col.id} value={col.name}>
                            {col.name} ({col.data_type})
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                </td>
                <td className={`${styles.gridTableCell} ${styles.gridTableCellCenter} text-blue-500`}>
                  →
                </td>
                <td className={styles.gridTableCell}>
                  <Select
                    value={newMapping.destination_table || ""}
                    onValueChange={(value) => setNewMapping({ ...newMapping, destination_table: value })}
                  >
                    <SelectTrigger className={styles.gridTableSelect}>
                      <SelectValue placeholder="Seleccionar tabla..." />
                    </SelectTrigger>
                    <SelectContent>
                      {destTables.map((t) => (
                        <SelectItem key={t.id} value={t.name}>
                          {t.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </td>
                <td className={styles.gridTableCell}>
                  <Select
                    value={newMapping.destination_column || ""}
                    onValueChange={(value) => setNewMapping({ ...newMapping, destination_column: value })}
                    disabled={!newMapping.destination_table}
                  >
                    <SelectTrigger className={styles.gridTableSelect}>
                      <SelectValue placeholder="Seleccionar columna..." />
                    </SelectTrigger>
                    <SelectContent>
                      {newMapping.destination_table &&
                        getColumnsForTable(newMapping.destination_table, "destination").map((col) => (
                          <SelectItem key={col.id} value={col.name}>
                            {col.name} ({col.data_type})
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                </td>
                <td className={styles.gridTableCell}>
                  <input
                    type="text"
                    placeholder="Notas opcionales..."
                    value={newMapping.notes || ""}
                    onChange={(e) => setNewMapping({ ...newMapping, notes: e.target.value })}
                    className={styles.gridTableInput}
                  />
                </td>
                <td className={styles.gridTableCell}>
                  <div className={styles.gridTableActions}>
                    <button
                      onClick={handleAddMapping}
                      className={`${styles.gridTableActionButton} ${styles.gridTableActionButtonSave}`}
                    >
                      <Save className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => {
                        setIsAddingNew(false);
                        setNewMapping({});
                      }}
                      className={`${styles.gridTableActionButton} ${styles.gridTableActionButtonCancel}`}
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>
            )}

            {/* Filas de datos */}
            {filteredAndSortedMappings.map((mapping, index) => (
              <tr key={index} className={styles.gridTableRow}>
                <td className={`${styles.gridTableCell} ${styles.gridTableCellMedium}`}>
                  {mapping.origin_table}
                </td>
                <td className={styles.gridTableCell}>
                  <span className={`${styles.gridTableBadge} ${styles.gridTableBadgeOrigin}`}>
                    {mapping.origin_column}
                  </span>
                </td>
                <td className={`${styles.gridTableCell} ${styles.gridTableCellCenter} text-muted-foreground`}>
                  →
                </td>
                <td className={`${styles.gridTableCell} ${styles.gridTableCellMedium}`}>
                  {mapping.destination_table}
                </td>
                <td className={styles.gridTableCell}>
                  <span className={`${styles.gridTableBadge} ${styles.gridTableBadgeDestination}`}>
                    {mapping.destination_column}
                  </span>
                </td>
                <td className={`${styles.gridTableCell} text-muted-foreground`}>
                  {mapping.notes || "-"}
                </td>
                <td className={styles.gridTableCell}>
                  <div className={styles.gridTableActions}>
                    <button
                      onClick={() => handleDeleteMapping(mapping)}
                      className={`${styles.gridTableActionButton} ${styles.gridTableActionButtonDelete}`}
                      title="Eliminar mapeo"
                    >
                      <Trash2 className="w-4 h-4 text-red-500" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}

            {filteredAndSortedMappings.length === 0 && (
              <tr>
                <td colSpan={7} className={styles.gridTableCellEmpty}>
                  {searchQuery
                    ? "No se encontraron mapeos con ese criterio"
                    : "No hay mapeos creados. Haz clic en 'Nuevo Mapeo' para comenzar."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div className={styles.gridFooter}>
        <div className={styles.gridFooterStats}>
          <div className={styles.gridFooterStat}>
            <span className={styles.gridFooterStatLabel}>Total mapeos:</span>
            <span className={styles.gridFooterStatValue}>{mappings.length}</span>
          </div>
          <div className={styles.gridFooterStat}>
            <span className={styles.gridFooterStatLabel}>Tablas origen:</span>
            <span className={styles.gridFooterStatValue}>{originTables.length}</span>
          </div>
          <div className={styles.gridFooterStat}>
            <span className={styles.gridFooterStatLabel}>Tablas destino:</span>
            <span className={styles.gridFooterStatValue}>{destTables.length}</span>
          </div>
        </div>
        <div className={styles.gridFooterHint}>
          Haz clic en los encabezados para ordenar
        </div>
      </div>
    </div>
  );
};