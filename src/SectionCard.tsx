import Card from "react-bootstrap/Card";
import { sectionInterval } from "./models";
import type { Section } from "./models";

type Props = {
  section: Section;
};

export default function SectionCard({ section }: Props) {
  return (
    <Card key={section.id} body>
      <Card.Subtitle>
        {section.name} @ {section.location}
      </Card.Subtitle>
      <Card.Text>{sectionInterval(section)}</Card.Text>
    </Card>
  );
}
