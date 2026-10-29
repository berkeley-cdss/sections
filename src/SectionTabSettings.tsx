import "bootstrap/dist/css/bootstrap.css";
import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Col from "react-bootstrap/Col";
import Form from "react-bootstrap/Form";
import Table from "react-bootstrap/Table";
import Container from "react-bootstrap/Container";
import Row from "react-bootstrap/Row";
import CalloutCard from "./CalloutCard";
import type { Message } from "./MessageContext";
import { getSectionStartTime, getSectionEndTime, getSectionDay } from "./models";
import type { ID, Section } from "./models";
import InfoTooltip from "./InfoTooltip";
import useAPI from "./useAPI";
import useSectionAPI from "./useSectionAPI";

type Props = {
  section: Section;
};

type StaffMember = { id: ID; name: string; email: string };

type SettingsKey = "staff" | "capacity" | "location" | "day" | "startTime" | "endTime" | "tags";

// staff holds the chosen staff member's id, or "" for unassigned.
type FormData = { [key in SettingsKey]: string };

// The form's fields as the section has them.
const savedValues = (section: Section): FormData => ({
  staff: section.staff?.id.toString() ?? "",
  capacity: section.capacity.toString(),
  location: section.location,
  day: getSectionDay(section),
  startTime: getSectionStartTime(section),
  endTime: getSectionEndTime(section),
  tags: section.tags.toString(),
});

const settings: Array<{ key: SettingsKey; label: string; tooltip: string }> = [
  {
    key: "staff",
    label: "Staff Member",
    tooltip:
      "TAs and teachers in this course on bCourses who have signed in to Sections, plus anyone listed in an imported Sections sheet who hasn't signed in yet.",
  },
  { key: "capacity", label: "Capacity", tooltip: "At least the number of students enrolled (Ex: 35)" },
  { key: "location", label: "Location", tooltip: "Any text (Ex: Wheeler 150)" },
  { key: "day", label: "Day", tooltip: "Any of: [M, T, W, Th, F] (Ex: M)" },
  { key: "startTime", label: "Start Time", tooltip: "A time with am or pm (Ex: 8:30 AM, 2:15pm or 08:30a)" },
  { key: "endTime", label: "End Time", tooltip: "A time with am or pm (Ex: 8:30 AM, 2:15pm or 08:30a)" },
  { key: "tags", label: "Tags", tooltip: "Comma seperated tags (Ex: Tag A, Tag B)" },
];

export default function SectionTabSettings({ section }: Props) {
  // Counts the changes that succeeded; a failed one shows its error at the top of the page.
  const saved = useRef(0);
  const onSaved = useCallback(() => {
    saved.current += 1;
  }, []);
  const changeLocationAPI = useSectionAPI("update_section_location", onSaved);
  const changeTagsAPI = useSectionAPI("update_section_tags", onSaved);
  const changeTimeAPI = useSectionAPI("update_section_time", onSaved);
  const changeStaffAPI = useSectionAPI("update_section_staff", onSaved);
  const changeCapacityAPI = useSectionAPI("update_section_capacity", onSaved);

  const [staffList, setStaffList] = useState<Array<StaffMember>>([]);
  const listStaffAPI = useAPI("list_staff", setStaffList);
  useEffect(() => {
    listStaffAPI();
  }, [listStaffAPI]);

  const [saving, setSaving] = useState(false);
  // Shown beside the button, since the page's messages are out of view up top.
  const [status, setStatus] = useState<Message | null>(null);
  const [formData, setFormData] = useState<FormData>(() => savedValues(section));
  // After submitting, show what was saved, so a rejected value isn't sent again.
  const fetchSectionAPI = useSectionAPI(
    "fetch_section",
    useCallback((saved: Section) => setFormData(savedValues(saved)), [])
  );

  // The current staff member, even if they're no longer on the course's staff.
  const staffOptions =
    section.staff != null && !staffList.some((staff) => staff.id === section.staff?.id.toString())
      ? [{ ...section.staff, id: section.staff.id.toString() }, ...staffList]
      : staffList;

  const handleSubmit = async () => {
    // Each change is its own request; send them one at a time so each
    // response's section details are applied in order.
    const changes: Array<() => Promise<void>> = [];

    if (formData.staff !== (section.staff?.id.toString() ?? "")) {
      changes.push(() => changeStaffAPI({ section_id: section.id, staff_id: formData.staff }));
    }

    if (formData.capacity !== section.capacity.toString()) {
      changes.push(() => changeCapacityAPI({ section_id: section.id, capacity: formData.capacity }));
    }

    if (formData.location !== section.location) {
      changes.push(() =>
        changeLocationAPI({
          section_id: section.id,
          new_location: formData.location,
        })
      );
    }

    if (
      formData.day !== getSectionDay(section) ||
      formData.startTime !== getSectionStartTime(section) ||
      formData.endTime !== getSectionEndTime(section)
    ) {
      changes.push(() =>
        changeTimeAPI({
          section_id: section.id,
          day: formData.day,
          start_time: formData.startTime,
          end_time: formData.endTime,
        })
      );
    }

    if (formData.tags !== section.tags.toString()) {
      changes.push(() =>
        changeTagsAPI({
          section_id: section.id,
          tags: formData.tags,
        })
      );
    }

    if (changes.length === 0) {
      setStatus({ text: "There are no changes to save.", variant: "info" });
      return;
    }

    setStatus(null);
    setSaving(true);
    saved.current = 0;
    for (const change of changes) {
      await change();
    }
    await fetchSectionAPI({ section_id: section.id });
    setSaving(false);
    if (saved.current === changes.length) {
      setStatus({ text: "Section settings saved.", variant: "success" });
    } else {
      setStatus({
        text: `Saved ${saved.current} of ${changes.length} changes. See the error at the top of the page. The fields now show the saved values.`,
        variant: "danger",
      });
    }
  };

  const handleChange = (key: SettingsKey, value: string) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <Container>
      <br />
      <Row>
        <Col>
          <div className="mb-3">
            <CalloutCard
              header="Warning!"
              body="You can modify section attributes here, but changes should be made infrequently and carefully.
              Please ensure that this is necessary before proceeding."
            />
          </div>
        </Col>
      </Row>
      <Table striped hover>
        <thead>
          <tr>
            <th>Section Attribute</th>
            <th>Displayed Values</th>
          </tr>
        </thead>
        <tbody>
          {settings.map(({ key, label, tooltip }) => (
            <tr key={key}>
              <td>
                {label}
                <InfoTooltip text={tooltip} />
              </td>
              <td>
                {key === "staff" ? (
                  <Form.Select
                    size="sm"
                    value={formData.staff}
                    onChange={(e) => handleChange("staff", e.target.value)}
                  >
                    <option value="">Unassigned</option>
                    {staffOptions.map((staff) => (
                      <option key={staff.id} value={staff.id}>
                        {staff.name} ({staff.email})
                      </option>
                    ))}
                  </Form.Select>
                ) : (
                  <input
                    type="text"
                    value={formData[key]}
                    onChange={(e) => handleChange(key, e.target.value)}
                  />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Button variant="primary" size="sm" onClick={handleSubmit} disabled={saving}>
        {saving ? "Saving…" : "Submit Changes"}
      </Button>
      {status != null ? (
        <Alert
          className="mt-3"
          variant={status.variant}
          onClose={() => setStatus(null)}
          dismissible
        >
          {status.text}
        </Alert>
      ) : null}
    </Container>
  );
}
