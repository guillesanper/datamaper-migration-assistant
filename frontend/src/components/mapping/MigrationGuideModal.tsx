import React from 'react';
import { useTranslation } from 'react-i18next';
import { HelpCircle } from 'lucide-react';
import { X } from '../icons';
import { type GenerateScriptOptions } from '../../services/migration_service';
import styles from '../../styles/mapping/mapping.module.css';

interface MigrationGuideModalProps {
  isOpen: boolean;
  onClose: () => void;
  dialect: GenerateScriptOptions['dialect'];
}

const codeBlock = (content: string) => (
  <pre
    style={{
      background: 'hsl(220 14% 10%)',
      color: 'hsl(210 40% 90%)',
      padding: '0.75rem 1rem',
      borderRadius: '0.5rem',
      fontSize: '0.8125rem',
      fontFamily: 'monospace',
      overflowX: 'auto',
      margin: 0,
      lineHeight: 1.6,
    }}
  >
    {content}
  </pre>
);

const DIALECT_LABELS: Record<GenerateScriptOptions['dialect'], string> = {
  postgresql: 'PostgreSQL',
  mysql: 'MySQL',
  sqlserver: 'SQL Server',
  oracle: 'Oracle',
};

interface DialectGuide {
  cliTool: string;
  cliCommand: string;
  guiTools: string;
  pythonPackage: string;
  pythonCode: string;
}

const DIALECT_GUIDES: Record<GenerateScriptOptions['dialect'], DialectGuide> = {
  postgresql: {
    cliTool: 'psql',
    cliCommand: 'psql -h HOST -p PUERTO -U USUARIO -d BASE_DE_DATOS -f migration_XXXX.sql',
    guiTools: 'pgAdmin / DBeaver / TablePlus',
    pythonPackage: 'psycopg2',
    pythonCode: `import psycopg2

conn = psycopg2.connect("host=HOST dbname=DB user=USER password=PASS")
cur = conn.cursor()
with open("migration_XXXX.sql") as f:
    cur.execute(f.read())
conn.commit()
cur.close()
conn.close()`,
  },
  mysql: {
    cliTool: 'mysql',
    cliCommand: 'mysql -h HOST -P PUERTO -u USUARIO -p BASE_DE_DATOS < migration_XXXX.sql',
    guiTools: 'MySQL Workbench / DBeaver / TablePlus',
    pythonPackage: 'mysql-connector-python',
    pythonCode: `import mysql.connector

conn = mysql.connector.connect(
    host="HOST", user="USUARIO", password="PASS", database="DB"
)
cur = conn.cursor()
with open("migration_XXXX.sql") as f:
    for statement in f.read().split(";"):
        if statement.strip():
            cur.execute(statement)
conn.commit()
cur.close()
conn.close()`,
  },
  sqlserver: {
    cliTool: 'sqlcmd',
    cliCommand: 'sqlcmd -S HOST -U USUARIO -P CONTRASEÑA -d BASE_DE_DATOS -i migration_XXXX.sql',
    guiTools: 'SQL Server Management Studio (SSMS) / DBeaver / Azure Data Studio',
    pythonPackage: 'pyodbc',
    pythonCode: `import pyodbc

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=HOST;DATABASE=DB;UID=USUARIO;PWD=PASS"
)
cur = conn.cursor()
with open("migration_XXXX.sql") as f:
    cur.execute(f.read())
conn.commit()
cur.close()
conn.close()`,
  },
  oracle: {
    cliTool: 'sqlplus',
    cliCommand: 'sqlplus USUARIO/CONTRASEÑA@HOST/BASE_DE_DATOS @migration_XXXX.sql',
    guiTools: 'SQL Developer / DBeaver / Toad for Oracle',
    pythonPackage: 'cx_Oracle',
    pythonCode: `import cx_Oracle

conn = cx_Oracle.connect("USUARIO/CONTRASEÑA@HOST/DB")
cur = conn.cursor()
with open("migration_XXXX.sql") as f:
    cur.execute(f.read())
conn.commit()
cur.close()
conn.close()`,
  },
};

export const MigrationGuideModal: React.FC<MigrationGuideModalProps> = ({ isOpen, onClose, dialect }) => {
  const { t } = useTranslation('mapping' as any);

  if (!isOpen) return null;

  const cliNote = t(`guide.dialects.${dialect}.cliNote` as any);
  const guiSteps = [
    t(`guide.dialects.${dialect}.guiStep1` as any),
    t(`guide.dialects.${dialect}.guiStep2` as any),
    t(`guide.dialects.${dialect}.guiStep3` as any),
    t(`guide.dialects.${dialect}.guiStep4` as any),
  ];
  const params = [
    { name: t('guide.params.batchSize' as any), desc: t('guide.params.batchSizeHint' as any) },
    { name: t('guide.params.dryRun' as any),    desc: t('guide.params.dryRunHint' as any) },
    { name: t('guide.params.constraints' as any), desc: t('guide.params.constraintsHint' as any) },
    { name: t('guide.params.validation' as any), desc: t('guide.params.validationHint' as any) },
  ];

  const guide = DIALECT_GUIDES[dialect];
  const dialectLabel = DIALECT_LABELS[dialect];

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 60,
        background: 'rgba(0,0,0,0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1rem',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--color-card)',
          borderRadius: '0.75rem',
          width: '100%',
          maxWidth: '46rem',
          maxHeight: '85vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
          border: '1px solid hsl(var(--border))',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '1.25rem 1.5rem',
            borderBottom: '1px solid hsl(var(--border))',
            background: 'hsl(var(--muted) / 0.3)',
            borderRadius: '0.75rem 0.75rem 0 0',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
            <HelpCircle style={{ width: '1.125rem', height: '1.125rem', color: 'hsl(var(--primary))' }} />
            <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0 }}>
              {t('guide.title' as any, { dialect: dialectLabel })}
            </h3>
          </div>
          <button onClick={onClose} className={styles.modalCloseButton}>
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div
          className={styles.guideModalScrollable}
          style={{
            overflowY: 'auto',
            padding: '1.5rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '1.5rem',
          }}
        >
          {/* CLI */}
          <section>
            <h4 style={{ fontSize: '0.9375rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              {t('guide.cli.title' as any, { tool: guide.cliTool })}
            </h4>
            <p style={{ fontSize: '0.875rem', color: 'hsl(var(--muted-foreground))', marginBottom: '0.5rem' }}>
              {t('guide.cli.download' as any)}
            </p>
            {codeBlock(guide.cliCommand)}
            <p style={{ fontSize: '0.8125rem', color: 'hsl(var(--muted-foreground))', marginTop: '0.375rem' }}>
              {cliNote}
            </p>
          </section>

          {/* GUI */}
          <section>
            <h4 style={{ fontSize: '0.9375rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              {t('guide.gui.title' as any, { tools: guide.guiTools })}
            </h4>
            <ol style={{ fontSize: '0.875rem', color: 'hsl(var(--muted-foreground))', paddingLeft: '1.25rem', margin: 0, lineHeight: 1.8 }}>
              {guiSteps.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
          </section>

          {/* Python */}
          <section>
            <h4 style={{ fontSize: '0.9375rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              {t('guide.python.title' as any, { package: guide.pythonPackage })}
            </h4>
            {codeBlock(guide.pythonCode)}
          </section>

          {/* Parámetros */}
          <section>
            <h4 style={{ fontSize: '0.9375rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              {t('guide.params.title' as any)}
            </h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
              {params.map((p) => (
                <div key={p.name} style={{ display: 'flex', gap: '0.75rem', fontSize: '0.875rem' }}>
                  <code style={{ fontFamily: 'monospace', fontWeight: 600, color: 'hsl(var(--primary))', whiteSpace: 'nowrap', minWidth: '7rem' }}>{p.name}</code>
                  <span style={{ color: 'hsl(var(--muted-foreground))', lineHeight: 1.5 }}>{p.desc}</span>
                </div>
              ))}
            </div>
          </section>

          {/* Tips */}
          <section>
            <h4 style={{ fontSize: '0.9375rem', fontWeight: 600, marginBottom: '0.5rem' }}>
              {t('guide.tips.title' as any)}
            </h4>
            <ul style={{ fontSize: '0.875rem', color: 'hsl(var(--muted-foreground))', paddingLeft: '1.25rem', margin: 0, lineHeight: 1.8 }}>
              <li>{t('guide.tips.backup' as any)}</li>
              <li>{t('guide.tips.dryRunFirst' as any)}</li>
              <li>{t('guide.tips.rowsApprox' as any)}</li>
              <li>{t('guide.tips.transactions' as any)}</li>
              <li>{t('guide.tips.largeTable' as any)}</li>
            </ul>
          </section>
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '1rem 1.5rem',
            borderTop: '1px solid hsl(var(--border))',
            display: 'flex',
            justifyContent: 'flex-end',
          }}
        >
          <button onClick={onClose} className={styles.toolbarButtonPrimary}>
            {t('guide.close' as any)}
          </button>
        </div>
      </div>
    </div>
  );
};
