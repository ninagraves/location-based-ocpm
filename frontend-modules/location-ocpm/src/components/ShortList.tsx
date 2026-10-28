// A list shortened to its first entries, with "+ n more" showing the full list on hover.
// Used where a list can grow with the log, e.g. object types (docs/pages/overview.md, "Key numbers").
import { Text, Tooltip } from "@mantine/core";

/** How many entries are shown before "+ n more". */
export const SHORT_LIST_LIMIT = 5;

/**
 * The first `limit` items joined by `separator`; if there are more, a dotted "+ n more"
 * follows whose hover shows all items, one per line.
 *
 * @param items - The entries, already in display order (e.g. largest first).
 * @param limit - Entries shown before "+ n more" (default `SHORT_LIST_LIMIT`).
 * @param separator - Text between entries (default " · ").
 */
export const ShortList = ({
  items,
  limit = SHORT_LIST_LIMIT,
  separator = " · ",
}: {
  items: string[];
  limit?: number;
  separator?: string;
}) => {
  const hidden = items.length - limit;
  if (hidden <= 0) return <>{items.join(separator)}</>;
  return (
    <>
      {items.slice(0, limit).join(separator)}
      {separator}
      <Tooltip label={items.join("\n")} multiline maw={360} style={{ whiteSpace: "pre-line" }} withArrow>
        <Text span inherit td="underline" style={{ textDecorationStyle: "dotted", cursor: "help" }}>
          + {hidden.toLocaleString("en-GB")} more
        </Text>
      </Tooltip>
    </>
  );
};
