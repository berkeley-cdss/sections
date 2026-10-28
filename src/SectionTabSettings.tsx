import "bootstrap/dist/css/bootstrap.css";
import { useState } from "react";
import Button from "react-bootstrap/Button";
import Col from "react-bootstrap/Col";
import Table from "react-bootstrap/Table";
import Container from "react-bootstrap/Container";
import Row from "react-bootstrap/Row";
import CalloutCard from "./CalloutCard";
import { getSectionStartTime, getSectionEndTime, getSectionDay } from "./models";
import type { Section } from "./models";
import InfoTooltip from "./InfoTooltip";
import useSectionAPI from "./useSectionAPI";

type Props = {
  section: Section;
};

type SettingsKey = "staff" | "capacity" | "location" | "day" | "startTime" | "endTime" | "tags";

type FormData = { [key in SettingsKey]: string };

const settings: Array<{ key: SettingsKey; label: string; tooltip: string }> = [
  {
    key: "staff",
    label: "Staff Email",
    tooltip:
      "Email of a staff member in this course, or blank for unassigned (Ex: oski@berkeley.edu)",
  },
  {
    key: "capacity",
    label: "Capacity",
    tooltip: "At least the number of students enrolled (Ex: 35)",
  },
  { key: "location", label: "Location", tooltip: "Any text (Ex: Wheeler 150)" },
  { key: "day", label: "Day", tooltip: "Any of: [M, T, W, Th, F] (Ex: M)" },
  { key: "startTime", label: "Start Time", tooltip: "hh:mma/p Include leading 0 (Ex: 08:30a)" },
  { key: "endTime", label: "End Time", tooltip: "hh:mma/p Include leading 0 (Ex: 08:30a)" },
  { key: "tags", label: "Tags", tooltip: "Comma seperated tags (Ex: Tag A, Tag B)" },
];

export default function SectionTabSettings({ section }: Props) {
  const changeLocationAPI = useSectionAPI("update_section_location");
  const changeTagsAPI = useSectionAPI("update_section_tags");
  const changeTimeAPI = useSectionAPI("update_section_time");
  const changeStaffAPI = useSectionAPI("update_section_staff");
  const changeCapacityAPI = useSectionAPI("update_section_capacity");

  const [formData, setFormData] = useState<FormData>({
    staff: section.staff?.email ?? "",
    capacity: section.capacity.toString(),
    location: section.location,
    day: getSectionDay(section),
    startTime: getSectionStartTime(section),
    endTime: getSectionEndTime(section),
    tags: section.tags.toString(),
  });

  const handleSubmit = () => {
    if (formData.staff !== (section.staff?.email ?? "")) {
      changeStaffAPI({
        section_id: section.id,
        email: formData.staff,
      });
    }

    if (formData.capacity !== section.capacity.toString()) {
      changeCapacityAPI({
        section_id: section.id,
        capacity: formData.capacity,
      });
    }

    if (formData.location !== section.location) {
      changeLocationAPI({
        section_id: section.id,
        new_location: formData.location,
      });
    }

    if (
      formData.day !== getSectionDay(section) ||
      formData.startTime !== getSectionStartTime(section) ||
      formData.endTime !== getSectionEndTime(section)
    ) {
      changeTimeAPI({
        section_id: section.id,
        day: formData.day,
        start_time: formData.startTime,
        end_time: formData.endTime,
      });
    }

    if (formData.tags !== section.tags.toString()) {
      changeTagsAPI({
        section_id: section.id,
        tags: formData.tags,
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
                <input
                  type="text"
                  value={formData[key]}
                  onChange={(e) => handleChange(key, e.target.value)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Button variant="primary" size="sm" onClick={handleSubmit}>
        Submit Changes
      </Button>
    </Container>
  );
}
