// Module definition: name, label and pages of the module.
import { defineModule, defineModuleRoute } from "@ocelescope/core";
import { MapPinnedIcon } from "lucide-react";
import Configuration from "./routes/Configuration";
import DirectlyFollowsGraph from "./routes/DirectlyFollowsGraph";
import Instances from "./routes/Instances";

const configurationRoute = defineModuleRoute({
  name: "configuration",
  label: "Configuration",
  requiresOcel: true,
  component: Configuration,
});

const dfgRoute = defineModuleRoute({
  name: "dfg",
  label: "Directly-follows graph",
  requiresOcel: true,
  component: DirectlyFollowsGraph,
});

const instancesRoute = defineModuleRoute({
  name: "instances",
  label: "Instances",
  requiresOcel: true,
  component: Instances,
});

export default defineModule({
  name: "locationBasedOcpm",
  label: "Location-based OCPM",
  description: "Location-based object-centric process mining for production and logistics",
  authors: [{ name: "Nina Graves" }],
  icon: MapPinnedIcon,
  routes: [configurationRoute, dfgRoute, instancesRoute],
});
