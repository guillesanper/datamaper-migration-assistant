// src/components/mapping/importExamples.ts
// Ejemplos del formato de importación de estructura que muestra ImportModal.
// Se generan a partir de datos tipados para que sigan siempre el formato real que
// valida el backend (backend/app/static/schemas/table_import_schema.json).

export type ImportFormat = 'json' | 'csv' | 'excel';
export type ImportSide = 'origin' | 'destination' | 'both';

type TableSide = Exclude<ImportSide, 'both'>;
type ColumnType = 'TEXT' | 'INTEGER' | 'REAL' | 'BOOLEAN' | 'DATE' | 'DATETIME';

interface SampleColumn {
  name: string;
  type: ColumnType;
  isPrimary: boolean;
  isNullable: boolean;
}

interface SampleTable {
  name: string;
  type: TableSide;
  columns: SampleColumn[];
}

const col = (
  name: string,
  type: ColumnType,
  isPrimary = false,
  isNullable = false
): SampleColumn => ({ name, type, isPrimary, isNullable });

const SAMPLE_TABLES: Record<TableSide, SampleTable[]> = {
  origin: [
    {
      name: 'customers',
      type: 'origin',
      columns: [col('customer_id', 'INTEGER', true), col('full_name', 'TEXT'), col('email', 'TEXT', false, true)]
    },
    {
      name: 'orders',
      type: 'origin',
      columns: [col('order_id', 'INTEGER', true), col('order_date', 'DATE'), col('total', 'REAL')]
    }
  ],
  destination: [
    {
      name: 'dim_customer',
      type: 'destination',
      columns: [col('customer_key', 'INTEGER', true), col('name', 'TEXT'), col('is_active', 'BOOLEAN')]
    },
    {
      name: 'fact_orders',
      type: 'destination',
      columns: [col('order_key', 'INTEGER', true), col('ordered_at', 'DATETIME'), col('amount', 'REAL', false, true)]
    }
  ]
};

// "both" muestra una tabla de cada lado: es lo que cambia respecto a los otros dos casos.
const tablesFor = (side: ImportSide): SampleTable[] =>
  side === 'both'
    ? [SAMPLE_TABLES.origin[0], SAMPLE_TABLES.destination[0]]
    : SAMPLE_TABLES[side];

const CSV_HEADERS = ['table_name', 'type', 'column_name', 'data_type', 'is_primary', 'is_nullable'];

const toRows = (tables: SampleTable[]): string[][] =>
  tables.flatMap((table) =>
    table.columns.map((c) => [
      table.name,
      table.type,
      c.name,
      c.type,
      String(c.isPrimary),
      String(c.isNullable)
    ])
  );

const toJson = (tables: SampleTable[]): string => {
  const tableBlocks = tables.map((table) => {
    const columns = table.columns.map(
      (c) =>
        `        { "name": ${JSON.stringify(c.name)}, "type": "${c.type}", ` +
        `"is_primary": ${c.isPrimary}, "is_nullable": ${c.isNullable} }`
    );
    return [
      '    {',
      `      "name": ${JSON.stringify(table.name)},`,
      `      "type": "${table.type}",`,
      '      "columns": [',
      columns.join(',\n'),
      '      ]',
      '    }'
    ].join('\n');
  });
  return `{\n  "tables": [\n${tableBlocks.join(',\n')}\n  ]\n}`;
};

const toCsv = (tables: SampleTable[]): string =>
  [CSV_HEADERS, ...toRows(tables)].map((row) => row.join(',')).join('\n');

// Rejilla alineada: representa las celdas de la primera hoja del libro de Excel.
const toGrid = (tables: SampleTable[]): string => {
  const rows = [CSV_HEADERS, ...toRows(tables)];
  const widths = CSV_HEADERS.map((_, i) => Math.max(...rows.map((row) => row[i].length)));
  return rows.map((row) => row.map((cell, i) => cell.padEnd(widths[i])).join(' | ').trimEnd()).join('\n');
};

export const buildImportExample = (format: ImportFormat, side: ImportSide): string => {
  const tables = tablesFor(side);
  switch (format) {
    case 'json':
      return toJson(tables);
    case 'csv':
      return toCsv(tables);
    case 'excel':
      return toGrid(tables);
  }
};
