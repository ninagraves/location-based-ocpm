// Turn a failed request into the text shown to the user.

/** Read the error message of a failed request (the backend's `detail`, if it sent one). */
export const errorText = (error: unknown) => {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  return detail ? JSON.stringify(detail) : String(error);
};
