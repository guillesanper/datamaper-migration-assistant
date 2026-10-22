import 'i18next';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'common';
    resources: {
      common: {
        app: {
          name: string;
          loading: string;
        };
        actions: {
          save: string;
          cancel: string;
          delete: string;
          edit: string;
          create: string;
          confirm: string;
          back: string;
          close: string;
          search: string;
          filter: string;
          export: string;
          import: string;
          copy: string;
          refresh: string;
          download: string;
        };
        divider: {
          or: string;
        };
        errors: {
          generic: string;
          network: string;
          unauthorized: string;
          required: string;
          invalid_email: string;
          min_length: string;
          max_length: string;
        };
        language: {
          toggle_label: string;
          es: string;
          en: string;
        };
        roles: {
          owner: string;
          admin: string;
          editor: string;
          viewer: string;
          member: string;
        };
        status: {
          active: string;
          inactive: string;
          pending: string;
          completed: string;
          failed: string;
          paused: string;
          running: string;
          draft: string;
        };
        time: {
          now: string;
          minutes_one: string;
          minutes_other: string;
          hours_one: string;
          hours_other: string;
          days_one: string;
          days_other: string;
          since_last_month: string;
        };
      };
      auth: {
        actions: {
          backToLogin: string;
          changeEmail: string;
          forgotPassword: string;
          hasAccount: string;
          login: string;
          loginLoading: string;
          loginSuccess: string;
          noAccount: string;
          register: string;
          registerLoading: string;
          registerSuccess: string;
          resendCode: string;
          resendCountdown: string;
          verified: string;
          verify: string;
          verifying: string;
        };
        brand: {
          feature: {
            multidb: string;
            validation: string;
            visual: string;
          };
          subtitle: string;
          title: string;
        };
        form: {
          confirmPassword: { label: string };
          email: { label: string; placeholder: string };
          password: {
            hide: string;
            hint: string;
            label: string;
            placeholder: string;
            show: string;
          };
          username: { hint: string; label: string; placeholder: string };
          usernameOrEmail: { label: string; placeholder: string };
        };
        messages: {
          codeSent: string;
          emailVerified: string;
          loginSuccess: string;
          registerSuccess: string;
          verifyEmailFirst: string;
        };
        page: {
          login: { subtitle: string; title: string };
          register: { subtitle: string; title: string };
          verify: { subtitle: string; title: string };
        };
        validation: {
          code: { length: string };
          email: { first: string; invalid: string; required: string };
          fields: { required: string };
          password: { min: string; mismatch: string; required: string };
          username: { min: string; required: string };
        };
        verify: {
          code: { hint: string; label: string };
          emailHint: string;
          enterEmailSubtitle: string;
          hint: { inbox: string; resend: string; validity: string };
          noCode: string;
          sentTo: string;
        };
      };
      dashboard: {
        greeting: {
          afternoon: string;
          evening: string;
          morning: string;
        };
        migrations: {
          empty: string;
          emptyHint: string;
          failed: string;
          pending: string;
          running: string;
          success: string;
        };
        modals: {
          create: {
            budgetLabel: string;
            creatingBtn: string;
            db: {
              compatibleNote: string;
              incompatibleNote: string;
              mysql: string;
              oracle: string;
              other: string;
              postgres: string;
              sqlserver: string;
            };
            descLabel: string;
            descPlaceholder: string;
            destLabel: string;
            destPlaceholder: string;
            encryptionError: string;
            encryptionHint: string;
            encryptionSection: string;
            encryptionToggle: string;
            nameLabel: string;
            namePlaceholder: string;
            originLabel: string;
            originPlaceholder: string;
            passphraseHint: string;
            passphraseImportant: string;
            passphraseLabel: string;
            passphrasePlaceholder: string;
            progressLabel: string;
            statusLabel: string;
            submitBtn: string;
            title: string;
            validation: {
              budgetNegative: string;
              destRequired: string;
              nameMax: string;
              nameMin: string;
              nameRequired: string;
              originRequired: string;
              passphraseCasing: string;
              passphraseMin: string;
              passphraseNumber: string;
              passphraseRequired: string;
              progressRange: string;
            };
          };
          delete: {
            aboutToDelete: string;
            confirmError: string;
            confirmInstruction: string;
            confirmPlaceholder: string;
            consequence1: string;
            consequence2: string;
            consequence3: string;
            consequencesIntro: string;
            deletingBtn: string;
            error: string;
            progress: string;
            submitBtn: string;
            success: string;
            title: string;
            warning: string;
          };
          edit: {
            activateEncryption: string;
            confirmPassphrasePlaceholder: string;
            deactivateEncryption: string;
            encryptDanger: string;
            encryptedHint: string;
            encryptionActiveDesc: string;
            encryptionActive: string;
            encryptionActivate: string;
            encryptionError: string;
            encryptionInactiveDesc: string;
            newPassphrasePlaceholder: string;
            savingBtn: string;
            submitBtn: string;
            title: string;
            validation: {
              passphraseForChange: string;
            };
          };
          members: {
            addBtn: string;
            addSection: string;
            closeBtn: string;
            emailPlaceholder: string;
            emailRequired: string;
            empty: string;
            emptyHint: string;
            errors: {
              add: string;
              load: string;
              remove: string;
              updateRole: string;
            };
            membersSection_one: string;
            membersSection_other: string;
            ownerBadge: string;
            projectCreator: string;
            removeConfirm: string;
            title: string;
            you: string;
          };
        };
        notifications: {
          daysAgo_one: string;
          daysAgo_other: string;
          empty: string;
          hoursAgo_one: string;
          hoursAgo_other: string;
          markAllRead: string;
          markRead: string;
          minutesAgo_one: string;
          minutesAgo_other: string;
          now: string;
          title: string;
        };
        projectRow: {
          actions: {
            delete: string;
            edit: string;
            leave: string;
            members: string;
            team: string;
            versions: string;
          };
          badge: {
            member: string;
          };
          dbDest: string;
          dbOrigin: string;
          moreOptions: string;
          status: {
            active: string;
            completed: string;
            paused: string;
          };
        };
        quickActions: {
          addDbConnection: string;
          addDbConnectionSub: string;
          createProject: string;
          createProjectSub: string;
          newMigration: string;
          newMigrationSub: string;
        };
        recent: {
          migrations: {
            title: string;
          };
          projects: {
            empty: string;
            neverAccessed: string;
            title: string;
          };
          versions: {
            title: string;
          };
        };
        sections: {
          activitySocial: string;
          recent: string;
        };
        sidebar: {
          aria: {
            closeMenu: string;
            collapse: string;
            expand: string;
          };
          nav: {
            admin: string;
            dashboard: string;
            projects: string;
            settings: string;
            team: string;
          };
          user: {
            account: string;
            billing: string;
            help: string;
            logout: string;
            profile: string;
            settings: string;
          };
        };
        stat_card: {
          changeNegative: string;
          changePositive: string;
        };
        stats: {
          activeProjects: string;
          completed: string;
          totalBudget: string;
          totalProjects: string;
        };
        table: {
          empty: string;
          error: string;
          exportTitle: string;
          filter: {
            active: string;
            all: string;
            completed: string;
            paused: string;
          };
          header: {
            budget: string;
            databases: string;
            progress: string;
            project: string;
            status: string;
            updatedAt: string;
          };
          importTitle: string;
          migrateHint: string;
          newProject: string;
          retry: string;
          searchPlaceholder: string;
          title: string;
        };
        topbar: {
          aria: {
            notifications: string;
            openMenu: string;
            settings: string;
            theme: string;
            toggleLanguage: string;
          };
          search: {
            placeholder: string;
          };
        };
        versions: {
          added: string;
          created: string;
          deleted: string;
          empty: string;
          emptyHint: string;
          entity: {
            column: string;
            index: string;
            schema: string;
            table: string;
            view: string;
          };
          renamed: string;
          updated: string;
        };
      };
      settings: {
        apiKeys: {
          copy: { success: string };
          create: string;
          createFormTitle: string;
          description: string;
          empty: string;
          expiry: {
            '1y': string;
            '30d': string;
            '90d': string;
            label: string;
            none: string;
          };
          lastUsed: string;
          name: { label: string; placeholder: string };
          neverUsed: string;
          new: { acknowledge: string; title: string; warning: string };
          revoke: string;
          revokeConfirm: string;
          revokedSuccess: string;
          status: { revoked: string };
          table: {
            actions: string;
            created: string;
            expires: string;
            lastUsed: string;
            name: string;
            prefix: string;
          };
          title: string;
        };
        notifications: {
          comments: string;
          email: { description: string; title: string };
          projectInvitations: string;
          push: { description: string; title: string };
          save: { success: string };
          securityAlerts: string;
          versionUpdates: string;
        };
        page: { subtitle: string; title: string };
        preferences: {
          dateFormat: { label: string };
          defaultDb: { label: string; none: string };
          defaultExport: { label: string; placeholder: string };
          error: { load: string; retry: string };
          language: { en: string; es: string; label: string; placeholder: string };
          save: { btn: string; success: string };
          section: string;
          theme: { dark: string; label: string; light: string; system: string };
          timezone: { label: string; placeholder: string };
        };
        profile: {
          avatarLabel: string;
          cancelPhoto: string;
          changePassword: string;
          changePhoto: string;
          confirmPassword: string;
          confirmPasswordPlaceholder: string;
          currentPassword: string;
          email: { label: string; unverified: string; verified: string };
          error: { format: string; size: string };
          formats: string;
          name: { label: string; placeholder: string };
          newPassword: string;
          newPasswordPlaceholder: string;
          removePhoto: string;
          saveChanges: string;
          savePhoto: string;
          section: { info: string };
          success: {
            passwordUpdated: string;
            photoRemoved: string;
            photoUpdated: string;
            updated: string;
          };
          validation: { passwordMin: string; passwordMismatch: string };
        };
        security: {
          '2fa': {
            deactivate: {
              currentPassword: string;
              desc: string;
              title: string;
              totpCode: string;
            };
            description: string;
            disable: string;
            disabled: string;
            enable: string;
            enabled: string;
            setup: {
              cancel: string;
              placeholder: string;
              step1: string;
              step2: string;
              title: string;
              verify: string;
            };
            success: { disabled: string; enabled: string };
            title: string;
          };
          accessLog: {
            cols: { date: string; event: string; ip: string; severity: string };
            empty: string;
            title: string;
          };
          sessions: {
            cantRevoke: string;
            current: string;
            empty: string;
            revoke: string;
            revoked: string;
            title: string;
            unknownIp: string;
          };
        };
        tabs: {
          apiKeys: string;
          notifications: string;
          preferences: string;
          profile: string;
          security: string;
        };
      };
      team: {
        activity: {
          empty: string;
          entity: {
            column: string;
            mapping: string;
            member: string;
            project: string;
            table: string;
          };
          errors: { load: string };
          event: {
            created: string;
            deleted: string;
            memberAdded: string;
            memberRemoved: string;
            roleUpdated: string;
            unknown: string;
            updated: string;
            versionCreated: string;
            versionRestored: string;
          };
          refresh: string;
          subtitle: { all: string; project: string };
          title: string;
          viewMore: string;
        };
        comments: {
          count_one: string;
          count_other: string;
          delete: string;
          deleteConfirm: string;
          edited: string;
          empty: string;
          errors: {
            add: string;
            delete: string;
            load: string;
            toggleResolve: string;
          };
          hideResolved: string;
          placeholder: string;
          reply: string;
          replyPlaceholder: string;
          replyingTo: string;
          resolve: string;
          resolved: string;
          showResolved: string;
          submit: string;
          success: {
            added: string;
            deleted: string;
            reopened: string;
            resolved: string;
          };
          title: string;
          unresolvedCount: string;
        };
        members: {
          addBtn: string;
          addingBtn: string;
          count_one: string;
          count_other: string;
          emailOrUsername: string;
          emailPlaceholder: string;
          empty: { subtitle: string; title: string };
          errors: {
            add: string;
            emailRequired: string;
            load: string;
            remove: string;
            updateRole: string;
          };
          invite: string;
          joined: string;
          ownerBadge: string;
          projectCreator: string;
          remove: string;
          removeConfirm: string;
          restrictedAccess: string;
          restrictedDesc: string;
          role: { change: string };
          roleLabel: string;
          success: {
            added: string;
            removed: string;
            roleUpdated: string;
          };
          teamInfo: string;
          title: string;
          you: string;
        };
        page: {
          errors: { load: string };
          noProjects: { subtitle: string; title: string };
          title: string;
        };
        projectInfo: {
          createdAt: string;
          destination: string;
          origin: string;
          progress: string;
          status: string;
          updatedAt: string;
        };
        projectSelector: { empty: string; label: string; placeholder: string };
        stats: {
          contributors: string;
          lastActivity: string;
          openComments: string;
          title: string;
          totalCommits: string;
        };
      };
      version_control: {
        activityFeed: {
          empty: string;
          filters: {
            all: string;
            comments: string;
            locks: string;
            versions: string;
          };
          loading: string;
          loadingMore: string;
          title: string;
          today: string;
          types: {
            comment_added: string;
            default: string;
            lock_acquired: string;
            lock_released: string;
            mapping_created: string;
            mapping_deleted: string;
            mapping_updated: string;
            member_added: string;
            member_removed: string;
            member_role_changed: string;
            project_updated: string;
            table_imported: string;
            tag_created: string;
            version_created: string;
            version_restored: string;
          };
          yesterday: string;
        };
        collaboration: {
          disconnected: string;
          online_one: string;
          online_other: string;
          startEditing: string;
          stopEditing: string;
          tabs: {
            activity: string;
            comments: string;
            users: string;
            versions: string;
          };
          title: string;
          user: {
            editing: string;
            viewing: string;
          };
        };
        commentThread: {
          delete: string;
          edit: string;
          edited: string;
          empty: string;
          emptyHint: string;
          placeholder: string;
          react: string;
          reopen: string;
          replies_one: string;
          replies_other: string;
          reply: string;
          replyTo: string;
          resolve: string;
          resolved: string;
          send: string;
          submit: string;
        };
        compare: {
          base: string;
          changes: {
            added: string;
            modified: string;
            removed: string;
          };
          changes_one: string;
          changes_other: string;
          diff: {
            after: string;
            before: string;
            newValue: string;
            oldValue: string;
          };
          noChanges: string;
          section: {
            added: string;
            modified: string;
            removed: string;
          };
          summary: {
            added_one: string;
            added_other: string;
            modified_one: string;
            modified_other: string;
            removed_one: string;
            removed_other: string;
          };
          target: string;
          title: string;
          versionA: string;
          versionB: string;
        };
        filters: {
          active_one: string;
          active_other: string;
          allTypes: string;
          author: {
            all: string;
            label: string;
          };
          changeType: string;
          clear: string;
          date: {
            custom: string;
            label: string;
            month: string;
            today: string;
            week: string;
          };
          dateFrom: string;
          dateTo: string;
          entityType: string;
          entityTypes: {
            column: string;
            mapping: string;
            project: string;
            table: string;
            transformation: string;
          };
          results_one: string;
          results_other: string;
          search: string;
          searchPlaceholder: string;
          tags: { label: string };
          title: string;
        };
        help: {
          button: string;
          close: string;
          howCreated: {
            desc: string;
            item1: string;
            item2: string;
            item3: string;
            item4: string;
            snapshot: string;
            title: string;
          };
          howTags: {
            desc: string;
            step1: string;
            step2: string;
            step3: string;
            step4: string;
            title: string;
          };
          title: string;
        };
        history: {
          cancelCompare: string;
          compareHint: string;
          count_one: string;
          count_other: string;
          current: string;
          empty: string;
          loadMore: string;
          loading: string;
          title: string;
        };
        stats: {
          activity: {
            title: string;
            tooltip: string;
          };
          contributors: string;
          distribution: {
            create: string;
            delete: string;
            title: string;
            tooltip: {
              create: string;
              delete: string;
              update: string;
            };
            update: string;
          };
          lastCommit: string;
          lastVersion: string;
          mostChanged: string;
          tags: string;
          title: string;
          today: string;
          totalVersions: string;
        };
        tags: {
          color: { label: string };
          colors: {
            blue: string;
            gray: string;
            green: string;
            indigo: string;
            orange: string;
            pink: string;
            purple: string;
            red: string;
            yellow: string;
          };
          count_one: string;
          count_other: string;
          create: string;
          createError: string;
          createdBy: string;
          creating: string;
          deleteConfirm: string;
          deleteError: string;
          descLabel: string;
          descPlaceholder: string;
          empty: string;
          emptyHint: string;
          name: { label: string; placeholder: string };
          nameRequired: string;
          title: string;
          unknownUser: string;
          versionRequired: string;
        };
        version: {
          addTag: string;
          author: string;
          cancelCompare: string;
          changeTypes: {
            create: string;
            delete: string;
            update: string;
          };
          compare: string;
          date: string;
          download: string;
          message: { label: string; placeholder: string };
          parentVersion: string;
          restore: string;
          restoreConfirm: string;
          tag: string;
          viewDetails: string;
        };
      };
      mapping: {
        columnModal: {
          autogenerated: { hint: string; label: string };
          createBtn: string;
          createTitle: string;
          default: { label: string };
          dest: string;
          editTitle: string;
          name: {
            label: string;
            placeholder: string;
            validation: { format: string; required: string };
          };
          nullable: { hint: string; label: string };
          options: { label: string };
          origin: string;
          originNote: string;
          pk: { hint: string; label: string };
          savingBtn: string;
          tableLabel: string;
          toast: { created: string; error: string; updated: string };
          type: { label: string };
          typeChangeRisk: string;
          typeError: string;
          unique: { label: string };
          updateBtn: string;
          validatingType: string;
        };
        db: {
          actions: { cancel: string; connect: string; test: string };
          db: { label: string; placeholder: string };
          dialectLabel: string;
          footer: { connecting: string };
          host: { label: string; placeholder: string };
          oracle: { serviceName: string; sid: string };
          pass: { label: string };
          port: { label: string };
          tabDest: string;
          tabOrigin: string;
          test: { error: string; success: string };
          timeout: { label: string };
          title: string;
          toast: {
            connected: string;
            connectError: string;
            testError: string;
            testSuccess: string;
            unknownError: string;
          };
          typeLabel: string;
          user: { label: string; placeholder: string };
          validation: {
            dbMax: string;
            dbRequired: string;
            formErrors: string;
            hostMax: string;
            hostRequired: string;
            noDialect: string;
            oracleRequired: string;
            passRequired: string;
            portRange: string;
            portRequired: string;
            timeoutRange: string;
            userMax: string;
            userRequired: string;
          };
        };
        deleteColumn: {
          consequence1: string;
          deletingBtn: string;
          info: string;
          submitBtn: string;
          title: string;
          toast: { error: string; success: string };
          warning: string;
        };
        deleteTable: {
          confirm: string;
          consequence1: string;
          consequence2: string;
          consequence3: string;
          deletingBtn: string;
          irreversible: string;
          submitBtn: string;
          tableType: { dest: string; origin: string };
          title: string;
          toast: { error: string; success: string };
          warning: string;
        };
        export: {
          error: string;
          exporting: string;
          footer: { empty: string; loading: string; ready_one: string; ready_other: string };
          format: {
            csv: string; csvDesc: string; csvLabel: string;
            excel: string; excelDesc: string; excelLabel: string;
            json: string; jsonDesc: string; jsonLabel: string;
            label: string;
          };
          options: { dataTypes: string; metadata: string; sqlScript: string };
          stats: { destTables: string; originTables: string; total: string };
          submit: string;
          success: string;
          title: string;
          validation: { ok: string; warnings_one: string; warnings_other: string };
        };
        guide: {
          cli: { download: string; title: string };
          close: string;
          dialects: {
            mysql: { cliNote: string; guiStep1: string; guiStep2: string; guiStep3: string; guiStep4: string };
            oracle: { cliNote: string; guiStep1: string; guiStep2: string; guiStep3: string; guiStep4: string };
            postgresql: { cliNote: string; guiStep1: string; guiStep2: string; guiStep3: string; guiStep4: string };
            sqlserver: { cliNote: string; guiStep1: string; guiStep2: string; guiStep3: string; guiStep4: string };
          };
          gui: { title: string };
          params: {
            batchSize: string; batchSizeHint: string;
            constraints: string; constraintsHint: string;
            dryRun: string; dryRunHint: string;
            title: string;
            validation: string; validationHint: string;
          };
          python: { title: string };
          tips: {
            backup: string; dryRunFirst: string; largeTable: string;
            rowsApprox: string; title: string; transactions: string;
          };
          title: string;
        };
        import: {
          allExisted: string;
          duplicates: {
            label: string; replace: string; replaceHint: string;
            skip: string; skipHint: string;
          };
          error: { noFile: string };
          example: {
            excelHint: string;
            hint: { both: string; destination: string; origin: string };
            label: string; required: string;
          };
          file: { dropHint: string; dropTitle: string; label: string };
          footer: { empty: string; ready: string };
          format: { compatible: string; label: string; recommended: string; simple: string };
          importing: string;
          info: {
            direction: string; duplicates: string; duplicatesReplace: string;
            title: string; types: string;
          };
          nothingImported: string;
          result: {
            columnsAdded_one: string; columnsAdded_other: string;
            skipped_one: string; skipped_other: string;
            tablesAdded_one: string; tablesAdded_other: string;
            tablesReplaced_one: string; tablesReplaced_other: string;
          };
          submit: string;
          success: string;
          title: string;
          type: { both: string; destOnly: string; hint: string; label: string; originOnly: string };
        };
        migration: {
          alert: {
            dialectUnknown: string; dialectUnknownDesc: string;
            scriptOnly: string; scriptOnlyDesc: string;
            sessionActive: string;
          };
          aria: { close: string };
          backBtn: string;
          batchSize: { hint: string; label: string };
          cancelBtn: string;
          chips: {
            batch: string; constraints: string; dialect: string;
            dryRun: string; validation: string;
          };
          closeBtn: string;
          dialect: { label: string };
          dryRunAlert: string;
          dryRunAlertDesc: string;
          footer: { configure: string; inProgress: string; scriptId: string; scriptMode: string };
          generateBtn: string;
          generating: string;
          log: {
            col: { duration: string; n: string; rows: string; status: string; table: string; type: string };
            title_one: string; title_other: string;
          };
          options: { constraints: string; dryRun: string; dryRunHint: string; validation: string };
          result: {
            dryRunDesc: string; dryRunNo: string; dryRunOk: string; dryRunYes: string;
            failed: string; migratedCount: string; rolledBack: string;
            statDryRun: string; statRows: string; statSteps: string; success: string;
          };
          runBtn: string;
          running: { progress: string; rowsMigrated: string; starting: string; timeLeft: string };
          script: { copy: string; download: string; howTo: string; label: string; rowsNote: string };
          starting: string;
          stats: { estimatedDuration: string; estimatedRows: string; tablesLabel: string };
          status: { completing: string };
          statusLabels: {
            completed: string; dryRunOk: string; failed: string;
            pending: string; rolledBack: string; running: string;
          };
          steps: { config: string; execution: string; preview: string; result: string; scriptGenerated: string };
          title: string;
          toast: { copied: string; runError: string; scriptError: string; unknownError: string };
        };
        primaryKey: {
          columns: { empty: string; label: string; selection: string };
          compositeInfo: string;
          constraintName: { hint: string; label: string; optional: string };
          current: string;
          info: { desc: string; title: string };
          removeBtn: string;
          removeConfirm: string;
          savingBtn: string;
          submitBtn: string;
          title: string;
          titleWithTable: string;
          toast: {
            compositeSuccess: string;
            error: string;
            removeError: string;
            removed: string;
            success: string;
          };
          type: { composite: string; compositeTitle: string; label: string; single: string };
          updateBtn: string;
          validation: { maxColumns: string; required: string };
        };
        stats: {
          allMapped: string; dest: string; mappings: string; origin: string;
          unmapped_one: string; unmapped_other: string;
        };
        tableModal: {
          createBtn: string; createTitle: string; editTitle: string; info: string;
          name: {
            hint: string; label: string; placeholder: string;
            validation: { format: string; required: string };
          };
          savingBtn: string;
          toast: { created: string; updated: string };
          typeDest: string; typeLabel: string; typeOrigin: string; updateBtn: string;
        };
        toolbar: {
          autoLayout: string; connectionActive: string; connectionOff: string;
          connectionOn: string; export: string; hideGrid: string; import: string;
          refresh: string; runMigration: string; saveLayout: string; showGrid: string;
        };
        typeChange: {
          affectedRows: string;
          affectedRowsDesc: string;
          applying: string;
          backup: { desc: string; title: string };
          column: string;
          confirmBackup: string;
          confirmDanger: string;
          currentType: string;
          danger: { warning: string };
          examples: string;
          from: string;
          moreExamples: string;
          newType: string;
          recommendation: string;
          riskDesc: string;
          riskLevel: { danger: string; info: string; warning: string };
          title: string;
          to: string;
          warning: string;
        };
      };
    };
  }
}
