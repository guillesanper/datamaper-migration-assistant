import { apiService } from "./api.service";

export interface RecentVersion {
  id: string;
  project_id: string;
  project_name: string;
  entity_type: string;
  change_type: string;
  message: string | null;
  created_at: string;
  created_by_username: string;
}

class VersionService {
  async getRecentVersions(limit = 5): Promise<RecentVersion[]> {
    const response = await apiService.get<{ success: boolean; data: RecentVersion[] }>(
      `/api/versions/recent?limit=${limit}`
    );
    return response.data ?? [];
  }
}

export const versionService = new VersionService();
