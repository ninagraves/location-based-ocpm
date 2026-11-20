// Module definition: name, label and pages of the module.
import { defineModule, defineModuleRoute } from "@ocelescope/core";
import { MapPinnedIcon } from "lucide-react";
import DirectlyFollowsGraph from "./routes/DirectlyFollowsGraph";
import Instances from "./routes/Instances";
import Overview from "./routes/Overview";

const overviewRoute = defineModuleRoute({
  name: "overview",
  label: "Overview",
  requiresOcel: true,
  component: Overview,
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
  routes: [overviewRoute, dfgRoute, instancesRoute],
});
