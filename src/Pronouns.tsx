import type { Person } from "./models";

type Props = {
  of: Pick<Person, "pronouns"> | null | undefined;
};

// A person's pronouns, after their name, if they share them in bCourses.
export default function Pronouns({ of }: Props) {
  if (!of?.pronouns) {
    return null;
  }
  return <small className="text-muted fw-normal ms-1">({of.pronouns})</small>;
}
