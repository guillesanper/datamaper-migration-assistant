import { apiService } from './api.service';

/**
 * Response from passphrase verification endpoint
 *
 * SEGURIDAD:
 * - session_token ya NO se devuelve en la respuesta (se guarda en httpOnly cookie)
 * - Inmune a XSS - JavaScript no puede acceder al token
 * - Solo recibimos confirmación de éxito y tiempo de expiración
 */
interface VerifyPassphraseResponse {
  valid: boolean;
  expires_in_seconds?: number;
  message?: string;
  remaining_attempts?: number; // Cuando falla, indica intentos restantes
}

/**
 * Response from encryption status check
 */
interface EncryptionStatusResponse {
  project_id: string;
  encryption_enabled: boolean;
  has_encryption_config: boolean;
  created_at?: string;
}

/**
 * Response from encryption setup endpoint
 */
interface SetupEncryptionResponse {
  status: string;
  message: string;
  project_id: string;
  encryption_enabled: boolean;
}

/**
 * Response from encryption statistics endpoint
 */
interface EncryptionStatsResponse {
  project_id: string;
  total_tables: number;
  encrypted_tables: number;
  total_columns: number;
  encrypted_columns: number;
  total_mappings: number;
  encrypted_mappings: number;
  encryption_percentage: number;
}

/**
 * Service for managing project encryption operations
 * Handles passphrase verification, session management, and encryption status checks
 */
class EncryptionService {
  private readonly BASE_PATH = '/api/projects';

  /**
   * Check if a project has encryption enabled
   * @param projectId - UUID of the project
   * @returns Encryption status information
   */
  async checkEncryptionStatus(projectId: string): Promise<EncryptionStatusResponse> {
    return await apiService.get(`${this.BASE_PATH}/${projectId}/encryption/status`);
  }

  /**
   * Verify passphrase and create encryption session
   * @param projectId - UUID of the project
   * @param passphrase - User's passphrase for decryption
   * @returns Session token and expiration information
   */
  async verifyPassphrase(
    projectId: string,
    passphrase: string
  ): Promise<VerifyPassphraseResponse> {
    return await apiService.post(
      `${this.BASE_PATH}/${projectId}/encryption/verify`,
      { passphrase }
    );
  }

  /**
   * Set up encryption for a project (one-time operation)
   * @param projectId - UUID of the project
   * @param passphrase - User's chosen passphrase for encryption
   * @returns Setup confirmation
   */
  async setupEncryption(
    projectId: string,
    passphrase: string
  ): Promise<SetupEncryptionResponse> {
    return await apiService.post(
      `${this.BASE_PATH}/${projectId}/encryption/setup`,
      { passphrase }
    );
  }

  /**
   * Get encryption statistics for a project
   * @param projectId - UUID of the project
   * @returns Statistics about encrypted entities
   */
  async getEncryptionStats(projectId: string): Promise<EncryptionStatsResponse> {
    return await apiService.get(`${this.BASE_PATH}/${projectId}/encryption/stats`);
  }

  /**
   * Rotate encryption key for a project
   * @param projectId - UUID of the project
   * @param currentPassphrase - Current passphrase
   * @param newPassphrase - New passphrase to use
   * @returns Operation result
   */
  async rotateEncryptionKey(
    projectId: string,
    currentPassphrase: string,
    newPassphrase: string
  ): Promise<{ status: string; message: string }> {
    return await apiService.post(
      `${this.BASE_PATH}/${projectId}/encryption/rotate-key`,
      { current_passphrase: currentPassphrase, new_passphrase: newPassphrase }
    );
  }

  /**
   * Enable encryption for a project
   * @param projectId - UUID of the project
   * @returns Operation result
   */
  async enableEncryption(projectId: string): Promise<{ status: string; message: string }> {
    return await apiService.post(`${this.BASE_PATH}/${projectId}/encryption/enable`, {});
  }

  /**
   * Disable encryption for a project (dangerous operation)
   * @param projectId - UUID of the project
   * @returns Operation result
   */
  async disableEncryption(projectId: string): Promise<{ status: string; message: string }> {
    return await apiService.post(`${this.BASE_PATH}/${projectId}/encryption/disable`, {});
  }

  /**
   * Check system-wide encryption health
   * @returns Health check results
   */
  async checkEncryptionHealth(): Promise<{ status: string; message: string }> {
    return await apiService.get('/api/encryption/health');
  }
}

// Export singleton instance
export const encryptionService = new EncryptionService();

// Export types for use in components
export type {
  VerifyPassphraseResponse,
  EncryptionStatusResponse,
  SetupEncryptionResponse,
  EncryptionStatsResponse
};
