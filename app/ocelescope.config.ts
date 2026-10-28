import type { OcelescopeConfig } from "@ocelescope/core";
import management from "@ocelescope/management";
import locationBasedOcpmModule from "@instance/location-based-ocpm";

// `pnpm run add:frontend` adds local frontend modules here.
export default {
	modules: [management, locationBasedOcpmModule],
} satisfies OcelescopeConfig;
