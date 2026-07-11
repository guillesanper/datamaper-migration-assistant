// src/components/version_control/HelpGuide.tsx
import React, { useState } from 'react';
import { HelpCircle, X, CheckCircle2, GitBranch, Tag, Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../ui/button';
import styles from '../../styles/version_control/help-guide.module.css';

interface HelpGuideProps {
  className?: string;
}

export const HelpGuide: React.FC<HelpGuideProps> = ({ className }) => {
  const { t } = useTranslation('version_control');
  const [isOpen, setIsOpen] = useState(false);

  if (!isOpen) {
    return (
      <Button
        size="sm"
        variant="outline"
        onClick={() => setIsOpen(true)}
        className={className}
      >
        <HelpCircle size={16} />
        {t('help.button')}
      </Button>
    );
  }

  return (
    <div className={styles.overlay} onClick={() => setIsOpen(false)}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <div className={styles.headerTitle}>
            <HelpCircle size={24} />
            <h2>{t('help.title')}</h2>
          </div>
          <Button
            size="icon-sm"
            variant="ghost"
            onClick={() => setIsOpen(false)}
          >
            <X size={20} />
          </Button>
        </div>

        <div className={styles.content}>
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <GitBranch className={styles.sectionIcon} />
              <h3>{t('help.howCreated.title')}</h3>
            </div>
            <p className={styles.sectionText}>{t('help.howCreated.desc')}</p>
            <ul className={styles.list}>
              <li>
                <CheckCircle2 size={16} className={styles.checkIcon} />
                {t('help.howCreated.item1')}
              </li>
              <li>
                <CheckCircle2 size={16} className={styles.checkIcon} />
                {t('help.howCreated.item2')}
              </li>
              <li>
                <CheckCircle2 size={16} className={styles.checkIcon} />
                {t('help.howCreated.item3')}
              </li>
              <li>
                <CheckCircle2 size={16} className={styles.checkIcon} />
                {t('help.howCreated.item4')}
              </li>
            </ul>
            <div className={styles.infoBox}>
              <Info size={16} />
              <p>{t('help.howCreated.snapshot')}</p>
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <Tag className={styles.sectionIcon} />
              <h3>{t('help.howTags.title')}</h3>
            </div>
            <p className={styles.sectionText}>{t('help.howTags.desc')}</p>
            <ol className={styles.orderedList}>
              <li>{t('help.howTags.step1')}</li>
              <li>{t('help.howTags.step2')}</li>
              <li>{t('help.howTags.step3')}</li>
              <li>{t('help.howTags.step4')}</li>
            </ol>
          </section>
        </div>

        <div className={styles.footer}>
          <Button variant="default" onClick={() => setIsOpen(false)}>
            {t('help.close')}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default HelpGuide;
